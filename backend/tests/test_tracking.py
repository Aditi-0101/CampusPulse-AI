import asyncio
import os
import sys
import uuid
import pytest
import httpx
from httpx import ASGITransport
from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.database import init_db, AsyncSessionLocal
from backend.app.models.grievance import Grievance, GrievanceStatus, GrievanceCategory
from backend.app.models.approval import HumanApproval
from backend.app.main import app

import pytest_asyncio

AUTH_SUPERVISOR = {"X-Staff-Token": "staff-token-sharma-9102"}

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()

async def create_sample_grievance(
    title: str = "Hostel Wi-Fi Signal Loss",
    status: GrievanceStatus = GrievanceStatus.PENDING_APPROVAL,
    requires_approval: bool = True
) -> Grievance:
    """Helper to seed a grievance record for tracking tests."""
    async with AsyncSessionLocal() as db:
        tkt = f"TKT-TRK-{uuid.uuid4().hex[:6].upper()}"
        grievance = Grievance(
            ticket_number=tkt,
            student_anon_id="student_anon_999",
            location_ref="infra_zone_h3_fl2",
            title=title,
            description="Signal dropped continuously during peak evening hours.",
            category=GrievanceCategory.HOSTEL_WIFI,
            urgency="HIGH",
            status=status,
            recommended_department="Network Infrastructure Engineering (Specialized NOC)",
            recommended_sla_hours=4,
            ai_recommendation="Escalated: PoE hardware defect requires physical replacement.",
            requires_human_approval=requires_approval,
            escalation_reason="Hardware defect requires authorized human staff review.",
            conversation_id="conv_internal_secret_uuid",
            meko_context_used=True,
            meko_context_summary="Internal Meko search found PoE under-voltage incident notes.",
        )
        db.add(grievance)
        await db.commit()
        await db.refresh(grievance)
        return grievance

@pytest.mark.asyncio
async def test_track_valid_pending_grievance():
    """1. Valid ticket returns correct tracking information for a pending grievance."""
    grievance = await create_sample_grievance("Hostel 3 Wi-Fi Outage", GrievanceStatus.PENDING_APPROVAL)

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/grievances/{grievance.ticket_number}/track")
        assert res.status_code == 200
        data = res.json()

        assert data["ticket_number"] == grievance.ticket_number
        assert data["category"] == "HOSTEL_WIFI"
        assert data["title"] == "Hostel 3 Wi-Fi Outage"
        assert data["status"] == "PENDING_APPROVAL"
        assert data["is_awaiting_approval"] is True
        assert data["assigned_department"] == "Network Infrastructure Engineering (Specialized NOC)"
        assert "submitted_at" in data
        assert "awaiting operational review" in data["status_explanation"].lower()
        assert "pending review" in data["latest_update"].lower()
        print(f"\n[PASS] Valid Pending Tracking: Ticket={data['ticket_number']}, Status={data['status']}")

@pytest.mark.asyncio
async def test_track_unknown_ticket_returns_404():
    """2. Unknown or nonexistent ticket identifier returns HTTP 404."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/grievances/TKT-DOES-NOT-EXIST-0000/track")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
        print("[PASS] Nonexistent ticket properly returns HTTP 404.")

@pytest.mark.asyncio
async def test_track_privacy_no_internal_or_pii_fields_exposed():
    """3. Privacy check: Response never exposes internal reviewer tokens, student IDs, DB keys, or Meko raw notes."""
    grievance = await create_sample_grievance("Privacy Boundary Audit", GrievanceStatus.PENDING_APPROVAL)

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/grievances/{grievance.ticket_number}/track")
        assert res.status_code == 200
        data = res.json()

        # Strict whitelist of allowed student-facing fields
        ALLOWED_FIELDS = {
            "ticket_number",
            "category",
            "title",
            "status",
            "submitted_at",
            "assigned_department",
            "latest_update",
            "is_awaiting_approval",
            "status_explanation",
        }
        actual_keys = set(data.keys())
        assert actual_keys == ALLOWED_FIELDS, f"Unexpected extra fields exposed: {actual_keys - ALLOWED_FIELDS}"

        # Explicitly verify sensitive internal fields are ABSENT
        FORBIDDEN_FIELDS = [
            "id",
            "grievance_id",
            "student_anon_id",
            "location_ref",
            "conversation_id",
            "ai_recommendation",
            "meko_context_used",
            "meko_context_summary",
            "reviewer_id",
            "reviewer_role",
            "budget_authorized",
            "suggested_budget",
            "recommendation_snapshot",
            "escalation_reason",
            "X-Staff-Token",
            "token",
            "is_spending_authorized",
        ]
        for forbidden in FORBIDDEN_FIELDS:
            assert forbidden not in data, f"Privacy Violation: Internal field '{forbidden}' leaked in track response!"

        # Assert no sensitive substring leaks in serialized payload
        serialized = str(data).lower()
        assert "student_anon_999" not in serialized
        assert "conv_internal_secret_uuid" not in serialized
        print("[PASS] Privacy boundaries strictly verified: Zero internal fields leaked.")

@pytest.mark.asyncio
async def test_track_approved_grievance_status_display():
    """4. Approved complaint displays the approved status and operational progress appropriately."""
    grievance = await create_sample_grievance("PoE Replacement Authorized", GrievanceStatus.APPROVED)

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/grievances/{grievance.ticket_number}/track")
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "APPROVED"
        assert data["is_awaiting_approval"] is False
        assert "approved" in data["status_explanation"].lower()
        assert "authorized" in data["latest_update"].lower()
        assert data["assigned_department"] == "Network Infrastructure Engineering (Specialized NOC)"
        print(f"[PASS] Approved Tracking Display: Status={data['status']}, Update={data['latest_update']}")

@pytest.mark.asyncio
async def test_track_rejected_grievance_status_display():
    """5. Rejected complaint displays the rejection status and non-sensitive feedback appropriately."""
    grievance = await create_sample_grievance("Hardware Replacement Declined", GrievanceStatus.REJECTED)

    # Attach human approval rejection record
    async with AsyncSessionLocal() as db:
        approval_rec = HumanApproval(
            grievance_id=grievance.id,
            ticket_number=grievance.ticket_number,
            reviewer_id="staff_supervisor_sharma",
            reviewer_role="NOC_SUPERVISOR",
            decision="REJECTED",
            reason="Physical replacement rejected. Performing remote port cycle and software re-provisioning first.",
            budget_authorized=0.0,
        )
        db.add(approval_rec)
        await db.commit()

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/grievances/{grievance.ticket_number}/track")
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "REJECTED"
        assert data["is_awaiting_approval"] is False
        assert "could not be approved" in data["status_explanation"].lower()
        assert "remote port cycle" in data["latest_update"].lower()
        # Credentials remain strictly unexposed
        assert "staff_supervisor_sharma" not in data["latest_update"]
        assert "reviewer_id" not in data
        print(f"[PASS] Rejected Tracking Display: Status={data['status']}, Feedback present without credential leak.")

@pytest.mark.asyncio
async def test_track_is_read_only_and_cannot_modify_grievance():
    """6. Read-only verification: Querying track endpoint does not mutate database records or timestamps."""
    grievance = await create_sample_grievance("Read-Only Safety Verification", GrievanceStatus.PENDING_APPROVAL)
    initial_updated_at = grievance.updated_at

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/grievances/{grievance.ticket_number}/track")
        assert res.status_code == 200

    async with AsyncSessionLocal() as db:
        re_queried = await db.scalar(select(Grievance).where(Grievance.id == grievance.id))
        assert re_queried.status == GrievanceStatus.PENDING_APPROVAL
        assert re_queried.updated_at == initial_updated_at
        print("[PASS] Read-only integrity verified: GET /track does not mutate database state.")

@pytest.mark.asyncio
async def test_track_workflow_integration():
    """7. End-to-end integration: Fresh intake grievance is immediately trackable and reflects approval lifecycle."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Submit new grievance via intake API
        payload = {
            "title": "Wi-Fi drop in study room",
            "description": "Corridor Wi-Fi drops every 20 minutes in hostel 3 study wing.",
            "student_anon_id": "student_anon_test",
            "location_ref": "infra_zone_h3_fl2",
            "category": "HOSTEL_WIFI"
        }
        res_create = await client.post("/api/v1/grievances", json=payload)
        assert res_create.status_code == 201
        created = res_create.json()
        ticket_number = created["ticket_number"]

        # Step 2: Track immediately
        res_track = await client.get(f"/api/v1/grievances/{ticket_number}/track")
        assert res_track.status_code == 200
        track_data = res_track.json()
        assert track_data["ticket_number"] == ticket_number
        assert track_data["title"] == "Wi-Fi drop in study room"
        assert track_data["category"] == "HOSTEL_WIFI"

        # Step 3: If it required human approval, approve it via staff API
        if created.get("requires_human_approval"):
            assert track_data["is_awaiting_approval"] is True
            res_approve = await client.post(
                f"/api/v1/approvals/{ticket_number}/decision",
                json={
                    "decision": "APPROVED",
                    "reason": "Authorized technician field check."
                },
                headers=AUTH_SUPERVISOR
            )
            assert res_approve.status_code == 200

            # Step 4: Track again and verify updated status
            res_track_after = await client.get(f"/api/v1/grievances/{ticket_number}/track")
            assert res_track_after.status_code == 200
            track_after_data = res_track_after.json()
            assert track_after_data["status"] == "APPROVED"
            assert track_after_data["is_awaiting_approval"] is False
            assert "approved" in track_after_data["status_explanation"].lower()
            print(f"[PASS] Workflow lifecycle tracking complete: Initial={track_data['status']} -> Final={track_after_data['status']}")
        else:
            print(f"[PASS] Routine complaint tracked: Status={track_data['status']}")

if __name__ == "__main__":
    asyncio.run(test_track_valid_pending_grievance())
    asyncio.run(test_track_unknown_ticket_returns_404())
    asyncio.run(test_track_privacy_no_internal_or_pii_fields_exposed())
    asyncio.run(test_track_approved_grievance_status_display())
    asyncio.run(test_track_rejected_grievance_status_display())
    asyncio.run(test_track_is_read_only_and_cannot_modify_grievance())
    asyncio.run(test_track_workflow_integration())
    print("\n=== All Stage E.1 Tracking Tests Passed Successfully ===")
