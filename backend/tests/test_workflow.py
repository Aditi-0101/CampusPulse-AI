import asyncio
import os
import sys
import uuid
import pytest
from unittest.mock import patch, AsyncMock
import httpx
from httpx import ASGITransport
from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.config import settings
from backend.app.core.database import init_db, AsyncSessionLocal
from backend.app.core.meko import meko_client
from backend.app.models.grievance import Grievance, GrievanceStatus
from backend.app.schemas.grievance import GrievanceCreate
from backend.app.services.orchestrator import grievance_orchestrator
from backend.app.main import app

import pytest_asyncio

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()

@pytest.mark.asyncio
async def test_e2e_successful_workflow_api():
    """1. Successful complete Front Desk -> Dispatch workflow via API endpoint."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "title": "Wi-Fi disconnecting intermittently",
            "description": "Wi-Fi signal drops every 15 minutes during evening study hours.",
            "student_anon_id": "student_anon_user",
            "location_ref": "infra_zone_h3_fl2",
            "category": "HOSTEL_WIFI"
        }
        res = await client.post("/api/v1/grievances", json=payload)
        assert res.status_code == 201
        data = res.json()

        # Validate structured fields
        assert data["ticket_number"].startswith("TKT-")
        assert data["triage"]["category"] == "HOSTEL_WIFI"
        assert data["triage"]["urgency"] == "MEDIUM"
        assert data["dispatch"] is not None
        assert data["dispatch"]["recommended_department"] == "Campus IT & Network Helpdesk"
        assert data["status"] in ["TRIAGED", "PENDING_APPROVAL"]
        print(f"\n[PASS] E2E Workflow API: Ticket={data['ticket_number']}, Status={data['status']}")

@pytest.mark.asyncio
async def test_same_ticket_number_preserved_across_workflow():
    """2. Same ticket number preserved across both agents and database persistence."""
    async with AsyncSessionLocal() as db:
        grievance_in = GrievanceCreate(
            title="Hostel 3 corridor Wi-Fi unstable",
            description="Packet loss detected when connecting to campus portal.",
            location_ref="infra_zone_h3_fl2",
        )
        resp = await grievance_orchestrator.process_new_grievance(grievance_in, db)
        
        # Verify DB record matches returned ticket number
        db_ticket = await db.scalar(select(Grievance).where(Grievance.id == resp.grievance_id))
        assert db_ticket is not None
        assert db_ticket.ticket_number == resp.ticket_number
        assert db_ticket.ticket_number == resp.triage.ticket_number
        assert db_ticket.ticket_number == resp.dispatch.ticket_number
        print(f"[PASS] Ticket Preserved: {db_ticket.ticket_number} across all layers")

@pytest.mark.asyncio
async def test_workflow_with_meko_context_attribution():
    """3. Meko context found in cp-dispatch and correctly attributed to grievance."""
    # Seed diagnostic memory in cp-dispatch
    conv_id = await meko_client.conversation_create(
        title="Admin Incident Note - H3 PoE Defect",
        agent_role="dispatch",
        datapack_id=settings.MEKO_DATAPACK_DISPATCH,
    )
    diagnostic_note = "Hostel 3 Corridor AP-H3 has faulty PoE injector causing under-voltage hardware resets."
    add_res = await meko_client.memory_add(
        text=diagnostic_note,
        agent_role="dispatch",
        conversation_id=conv_id,
        datapack_id=settings.MEKO_DATAPACK_DISPATCH,
    )
    mem_id = add_res.get("results", [{}])[0].get("id")

    try:
        async with AsyncSessionLocal() as db:
            grievance_in = GrievanceCreate(
                title="Wi-Fi AP-H3 dropping connection continuously",
                description="Access point AP-H3 resets every 10 minutes in Hostel 3 corridor.",
                location_ref="infra_zone_h3_fl2",
            )
            resp = await grievance_orchestrator.process_new_grievance(grievance_in, db)

            assert resp.meko_context_used is True
            assert resp.requires_human_approval is True
            assert resp.status == "PENDING_APPROVAL"
            assert resp.dispatch.budget_currency == "INR"
            assert resp.dispatch.is_spending_authorized is False
            assert resp.dispatch.budget_status == "ILLUSTRATIVE_ESTIMATE"
            assert resp.dispatch.suggested_budget == 3500.0
            assert "poe injector" in resp.dispatch.recommendation_reason.lower() or "under-voltage" in resp.dispatch.recommendation_reason.lower()
            print(f"[PASS] Meko Attribution: used={resp.meko_context_used}, status={resp.status}, budget=₹{resp.dispatch.suggested_budget} ({resp.dispatch.budget_status})")
    finally:
        # Clean up seeded memory
        if mem_id:
            await meko_client.call_tool(
                tool_name="memory_delete_by_id",
                arguments={
                    "memory_id": mem_id,
                    "agent_id": "product_agent:dispatch",
                    "datapack_id": settings.MEKO_DATAPACK_DISPATCH,
                    "conversation_id": conv_id,
                },
                agent_role="dispatch"
            )

@pytest.mark.asyncio
async def test_workflow_no_meko_context_baseline():
    """4. No Meko context found - clean deterministic fallback."""
    async with AsyncSessionLocal() as db:
        grievance_in = GrievanceCreate(
            title="General internet query",
            description="How do I register a guest laptop on campus network?",
            location_ref="node_loc_unknown_999",
            category="OTHER"
        )
        resp = await grievance_orchestrator.process_new_grievance(grievance_in, db)

        assert resp.dispatch.meko_context_retrieved is False
        assert len(resp.dispatch.meko_supporting_facts) == 0
        assert resp.requires_human_approval is False
        assert resp.status == "TRIAGED"
        print(f"[PASS] No Context Baseline: status={resp.status}, meko_used={resp.meko_context_used}")

@pytest.mark.asyncio
async def test_front_desk_failure_handling():
    """5. Front Desk input failure correctly rejects request before invalid processing."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Title too short
        bad_payload = {
            "title": "Hi",
            "description": "Valid description text here",
            "location_ref": "infra_zone_h3_fl2"
        }
        res = await client.post("/api/v1/grievances", json=bad_payload)
        assert res.status_code == 422 or res.status_code == 400
        print("[PASS] Front Desk input validation properly rejected short input.")

@pytest.mark.asyncio
async def test_dispatch_failure_resilience_grievance_persisted():
    """6 & 9. Grievance remains safely persisted in DB even if Dispatch Agent fails."""
    async with AsyncSessionLocal() as db:
        grievance_in = GrievanceCreate(
            title="Wi-Fi router power fluctuation",
            description="Power fluctuation causes router restart in corridor.",
            location_ref="infra_zone_h3_fl2",
        )

        # Simulate unexpected Dispatch Agent crash/timeout
        with patch("backend.app.agents.dispatch.dispatch_agent.assess_dispatch", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.side_effect = RuntimeError("Simulated Dispatch Network Timeout")

            resp = await grievance_orchestrator.process_new_grievance(grievance_in, db)

            # Grievance must still be returned and persisted in DB
            assert resp.grievance_id > 0
            assert resp.triage is not None
            assert resp.dispatch is None

            # Verify DB persistence
            saved = await db.scalar(select(Grievance).where(Grievance.id == resp.grievance_id))
            assert saved is not None
            assert saved.status == GrievanceStatus.TRIAGED
            assert "Dispatch assessment failed" in saved.ai_recommendation
            print(f"[PASS] Resilient Persistence: Grievance #{saved.id} preserved in DB after dispatch failure.")

@pytest.mark.asyncio
async def test_duplicate_complaint_handling():
    """7. Duplicate complaint detected and properly flagged without duplicating tickets."""
    async with AsyncSessionLocal() as db:
        grievance_in = GrievanceCreate(
            title="Wi-Fi down again",
            description="Second report for the same outage in corridor zone.",
            location_ref="infra_zone_h3_fl2",
        )

        with patch("backend.app.agents.front_desk.front_desk_agent.triage_grievance", new_callable=AsyncMock) as mock_triage:
            from backend.app.schemas.grievance import FrontDeskTriageResult
            dup_ticket = f"TKT-DUP-{uuid.uuid4().hex[:6].upper()}"
            orig_ticket = f"TKT-ORIG-{uuid.uuid4().hex[:6].upper()}"
            mock_triage.return_value = FrontDeskTriageResult(
                ticket_number=dup_ticket,
                category="HOSTEL_WIFI",
                urgency="MEDIUM",
                is_duplicate=True,
                duplicate_ticket_ref=orig_ticket,
                conversation_id="conv_dup",
                meko_context_used=True,
                meko_context_summary=f"Linked to active ticket {orig_ticket}",
                student_acknowledgment=f"Linked to {orig_ticket}",
            )

            resp = await grievance_orchestrator.process_new_grievance(grievance_in, db)
            
            saved = await db.scalar(select(Grievance).where(Grievance.id == resp.grievance_id))
            assert saved.is_duplicate is True
            assert saved.duplicate_of_ticket == orig_ticket
            print(f"[PASS] Duplicate Complaint Flagged: is_duplicate={saved.is_duplicate}, original={saved.duplicate_of_ticket}")

@pytest.mark.asyncio
async def test_cross_datapack_security_enforcement():
    """8. Security check: Product agents cannot access each other's datapacks."""
    from backend.app.core.config import validate_agent_datapack

    with pytest.raises(PermissionError):
        validate_agent_datapack("frontdesk", settings.MEKO_DATAPACK_DISPATCH)
    with pytest.raises(PermissionError):
        validate_agent_datapack("dispatch", settings.MEKO_DATAPACK_FRONTDESK)
    with pytest.raises(PermissionError):
        validate_agent_datapack("frontdesk", settings.FORBIDDEN_DEV_DATAPACK_ID)

    print("[PASS] Cross-datapack security isolation strictly enforced.")

if __name__ == "__main__":
    asyncio.run(test_e2e_successful_workflow_api())
    asyncio.run(test_same_ticket_number_preserved_across_workflow())
    asyncio.run(test_workflow_with_meko_context_attribution())
    asyncio.run(test_workflow_no_meko_context_baseline())
    asyncio.run(test_front_desk_failure_handling())
    asyncio.run(test_dispatch_failure_resilience_grievance_persisted())
    asyncio.run(test_duplicate_complaint_handling())
    asyncio.run(test_cross_datapack_security_enforcement())
    print("\n=== All Stage C Integration Tests Passed Successfully ===")
