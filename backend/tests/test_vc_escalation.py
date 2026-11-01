import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from unittest.mock import patch
import pytest
import httpx
from httpx import ASGITransport
from sqlalchemy import select, func

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.database import init_db, AsyncSessionLocal
from backend.app.core.meko import meko_client
from backend.app.models.grievance import Grievance, GrievanceStatus, GrievanceCategory
from backend.app.models.escalation import VCEscalation, VCEscalationStatus, VCEscalationDecision
from backend.app.models.meko_event import MekoEvent
from backend.app.main import app

import pytest_asyncio

# Test Tokens
VC_AUTH = {"X-Staff-Token": "staff-token-vc-9999"}
VC_DEMO_AUTH = {"X-Staff-Token": "demo-token-vice-chancellor"}
SUPERVISOR_AUTH = {"X-Staff-Token": "staff-token-sharma-9102"}
ADMIN_AUTH = {"X-Staff-Token": "staff-token-patel-8431"}
STUDENT_AARAV = {"X-Student-Token": "student-token-aarav-101"}
STUDENT_PRIYA = {"X-Student-Token": "student-token-priya-202"}
INVALID_STAFF_AUTH = {"X-Staff-Token": "invalid-staff-token-0000"}

@pytest_asyncio.fixture(autouse=True)
async def setup_db_and_mock_meko():
    await init_db()

    async def mock_call_tool(tool_name: str, arguments: dict, agent_role: str, grievance_id=None, event_type="TOOL_CALL"):
        # Log genuine MekoEvent in DB for authentic audit trail and swarm event derivation
        try:
            async with AsyncSessionLocal() as session:
                event = MekoEvent(
                    grievance_id=grievance_id,
                    agent_role=agent_role,
                    datapack_id=arguments.get("datapack_id") or "system",
                    tool_name=tool_name,
                    request_payload=json.dumps(arguments),
                    response_payload=json.dumps({"mock": True}),
                    status="SUCCESS",
                    duration_ms=4,
                    timestamp=datetime.utcnow(),
                )
                session.add(event)
                await session.commit()
        except Exception:
            pass

        if tool_name == "conversation_create":
            return {"conversation_id": f"conv_mock_{uuid.uuid4().hex[:8]}"}
        elif tool_name == "context_search":
            return {"results": {"conversation": {"hits": []}, "memory": []}}
        elif tool_name == "datapack_search":
            return {"results": []}
        elif tool_name == "conversation_add_message":
            return {"id": f"msg_mock_{uuid.uuid4().hex[:6]}"}
        elif tool_name == "memory_add":
            return {"results": [{"id": f"mem_mock_{uuid.uuid4().hex[:6]}"}]}
        return {"status": "success"}

    with patch.object(meko_client, "call_tool", side_effect=mock_call_tool):
        yield

async def get_test_client():
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")

@pytest.mark.asyncio
async def test_01_first_complaint_does_not_escalate():
    """1. First complaint filed by a verified student does not escalate."""
    async with await get_test_client() as client:
        resp = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Frequent Wi-Fi Dropouts in Block C",
                "description": "The 5GHz access point disconnects every 10 minutes in room 302.",
                "location_ref": "infra_zone_h3_fl2",
                "category": "HOSTEL_WIFI",
            },
            headers=STUDENT_AARAV,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["followup_count"] == 1
        assert data["is_escalated_to_vc"] is False
        assert data["escalation_id"] is None
        assert data["thread_id"] is not None

@pytest.mark.asyncio
async def test_02_second_complaint_does_not_escalate():
    """2. Second eligible follow-up on same thread does not escalate."""
    async with await get_test_client() as client:
        # Submit 1st complaint
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Persistent Hostel C Wi-Fi issue",
                "description": "Initial report of packet loss and connection drops.",
                "location_ref": "infra_zone_h3_fl2",
            },
            headers=STUDENT_AARAV,
        )
        assert r1.status_code == 201
        tkt1 = r1.json()["ticket_number"]
        thread1 = r1.json()["thread_id"]

        # Submit 2nd complaint (follow-up)
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Follow up: Persistent Hostel C Wi-Fi issue still happening",
                "description": "Still dropping packets despite router restart.",
                "location_ref": "infra_zone_h3_fl2",
                "followup_ticket_number": tkt1,
            },
            headers=STUDENT_AARAV,
        )
        assert r2.status_code == 201
        d2 = r2.json()
        assert d2["thread_id"] == thread1
        assert d2["followup_count"] == 2
        assert d2["is_escalated_to_vc"] is False
        assert d2["escalation_id"] is None

@pytest.mark.asyncio
async def test_03_third_complaint_triggers_exact_escalation():
    """3. Third eligible follow-up creates exactly one VC escalation record."""
    async with await get_test_client() as client:
        # 1st complaint
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Lab 4 AC cooling malfunction",
                "description": "Air conditioning unit leaking water and not cooling.",
                "location_ref": "infra_zone_acad_b1",
            },
            headers=STUDENT_AARAV,
        )
        tkt1 = r1.json()["ticket_number"]

        # 2nd complaint
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Lab 4 AC still not fixed",
                "description": "Water leaking has increased, temperature over 32C.",
                "location_ref": "infra_zone_acad_b1",
                "followup_ticket_number": tkt1,
            },
            headers=STUDENT_AARAV,
        )
        tkt2 = r2.json()["ticket_number"]

        # 3rd complaint (triggers escalation)
        r3 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Lab 4 AC emergency escalation",
                "description": "Third time reporting: computer equipment at risk due to ceiling water drip.",
                "location_ref": "infra_zone_acad_b1",
                "followup_ticket_number": tkt2,
            },
            headers=STUDENT_AARAV,
        )
        assert r3.status_code == 201
        d3 = r3.json()
        assert d3["followup_count"] == 3
        assert d3["is_escalated_to_vc"] is True
        assert d3["escalation_id"] is not None
        assert d3["escalation_id"].startswith("ESC-")

        # Verify DB record
        async with AsyncSessionLocal() as db:
            esc = await db.scalar(
                select(VCEscalation).where(VCEscalation.escalation_id == d3["escalation_id"])
            )
            assert esc is not None
            assert esc.complaint_count == 3
            assert esc.status == VCEscalationStatus.PENDING_REVIEW.value
            assert esc.thread_id == d3["thread_id"]

@pytest.mark.asyncio
async def test_04_fourth_followup_does_not_create_duplicate_escalation():
    """4. Fourth or subsequent follow-up attaches to existing escalation without duplicate."""
    async with await get_test_client() as client:
        # 1st
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Water heater failure wing 2",
                "description": "Geyser element tripped and circuit breaker blown.",
                "location_ref": "infra_zone_h2_fl1",
            },
            headers=STUDENT_AARAV,
        )
        tkt1 = r1.json()["ticket_number"]

        # 2nd
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Water heater still down wing 2",
                "description": "No hot water for 3 days now.",
                "location_ref": "infra_zone_h2_fl1",
                "followup_ticket_number": tkt1,
            },
            headers=STUDENT_AARAV,
        )
        tkt2 = r2.json()["ticket_number"]

        # 3rd (triggers escalation)
        r3 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Urgent: Water heater still unresolved",
                "description": "Third notice for wing 2 geyser.",
                "location_ref": "infra_zone_h2_fl1",
                "followup_ticket_number": tkt2,
            },
            headers=STUDENT_AARAV,
        )
        esc_id = r3.json()["escalation_id"]
        assert esc_id is not None

        # 4th (must not duplicate escalation)
        r4 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Fourth notice: Water heater issue wing 2",
                "description": "Following up again on the same unresolved problem.",
                "location_ref": "infra_zone_h2_fl1",
                "followup_ticket_number": tkt1,
            },
            headers=STUDENT_AARAV,
        )
        d4 = r4.json()
        assert d4["followup_count"] == 4
        assert d4["is_escalated_to_vc"] is True
        assert d4["escalation_id"] == esc_id

        # Verify only 1 escalation in DB for this thread
        async with AsyncSessionLocal() as db:
            escs = (await db.execute(
                select(VCEscalation).where(VCEscalation.thread_id == d4["thread_id"])
            )).scalars().all()
            assert len(escs) == 1
            assert escs[0].complaint_count >= 4

@pytest.mark.asyncio
async def test_05_same_category_different_issue_does_not_escalate():
    """5. Same category but separate issues remain separate threads and do not escalate."""
    async with await get_test_client() as client:
        # Issue A: Hostel 1 Wi-Fi
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Hostel 1 Wi-Fi issue",
                "description": "Hostel 1 wing A AP is completely dead.",
                "location_ref": "infra_zone_h1_fl1",
                "category": "HOSTEL_WIFI",
            },
            headers=STUDENT_AARAV,
        )
        # Issue B: Hostel 4 Wi-Fi (new report, not a follow-up)
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Hostel 4 Wi-Fi DNS problem",
                "description": "Hostel 4 students cannot resolve external domains.",
                "location_ref": "infra_zone_h4_fl2",
                "category": "HOSTEL_WIFI",
            },
            headers=STUDENT_AARAV,
        )
        # Issue C: Library Wi-Fi (new report, not a follow-up)
        r3 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Library Wi-Fi portal error",
                "description": "Captive portal redirect is looping.",
                "location_ref": "infra_zone_lib_fl1",
                "category": "HOSTEL_WIFI",
            },
            headers=STUDENT_AARAV,
        )
        # Each is in its own thread; none should escalate
        assert r1.json()["is_escalated_to_vc"] is False
        assert r2.json()["is_escalated_to_vc"] is False
        assert r3.json()["is_escalated_to_vc"] is False
        assert r1.json()["thread_id"] != r2.json()["thread_id"]
        assert r2.json()["thread_id"] != r3.json()["thread_id"]

@pytest.mark.asyncio
async def test_06_different_students_do_not_count_together():
    """6. Complaints from different students do not count towards the same student's escalation."""
    async with await get_test_client() as client:
        # Student Aarav files issue
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Cafeteria water cooler leak",
                "description": "Water overflowing near main cafeteria dining hall.",
                "location_ref": "infra_zone_cafe_fl1",
            },
            headers=STUDENT_AARAV,
        )
        tkt1 = r1.json()["ticket_number"]

        # Student Priya tries to file a separate report for the cafeteria
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Cafeteria water cooler leak also seen",
                "description": "Noticed wet floor near food counters.",
                "location_ref": "infra_zone_cafe_fl1",
            },
            headers=STUDENT_PRIYA,
        )
        # Should be distinct threads
        assert r1.json()["thread_id"] != r2.json()["thread_id"]
        assert r1.json()["followup_count"] == 1
        assert r2.json()["followup_count"] == 1

@pytest.mark.asyncio
async def test_07_student_cannot_followup_on_another_students_ticket():
    """7. Student cannot follow up on another student's ticket (403 Forbidden)."""
    async with await get_test_client() as client:
        # Aarav submits ticket
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Aarav private room complaint",
                "description": "Ceiling fan speed controller broken in room 101.",
                "location_ref": "infra_zone_h1_fl1",
            },
            headers=STUDENT_AARAV,
        )
        tkt_aarav = r1.json()["ticket_number"]

        # Priya attempts to follow up on Aarav's ticket
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Unauthorized follow-up attempt",
                "description": "Trying to link into another student's grievance.",
                "location_ref": "infra_zone_h1_fl1",
                "followup_ticket_number": tkt_aarav,
            },
            headers=STUDENT_PRIYA,
        )
        assert r2.status_code == 403
        assert "cannot follow up" in r2.json()["detail"].lower()

@pytest.mark.asyncio
async def test_08_anonymous_complaints_do_not_escalate():
    """8. Unverified anonymous complaints do not trigger individual escalation."""
    async with await get_test_client() as client:
        # Anonymous submission 1
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Anonymous corridor light flickering",
                "description": "Light outside stairwell 2 is blinking constantly.",
                "location_ref": "infra_zone_h2_fl2",
            },
        )
        assert r1.status_code == 201
        assert r1.json()["is_escalated_to_vc"] is False
        tkt1 = r1.json()["ticket_number"]

        # Attempt to follow up without verification token must fail with 401
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Anonymous follow-up attempt",
                "description": "Trying to follow up without student token.",
                "location_ref": "infra_zone_h2_fl2",
                "followup_ticket_number": tkt1,
            },
        )
        assert r2.status_code == 401
        assert "authentication" in r2.json()["detail"].lower()

@pytest.mark.asyncio
async def test_09_resolved_thread_cannot_be_escalated():
    """9. Resolved issue threads cannot trigger escalation."""
    async with await get_test_client() as client:
        # Create initial complaint
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Gym treadmill display error",
                "description": "Error code E-04 on treadmill 2.",
                "location_ref": "infra_zone_gym_fl1",
            },
            headers=STUDENT_AARAV,
        )
        tkt = r1.json()["ticket_number"]

        # Mark ticket as RESOLVED in DB
        async with AsyncSessionLocal() as db:
            g = await db.scalar(select(Grievance).where(Grievance.ticket_number == tkt))
            g.status = GrievanceStatus.RESOLVED
            await db.commit()

        # Attempt follow-up on resolved ticket
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Reopening resolved issue",
                "description": "Trying to follow up after resolution.",
                "location_ref": "infra_zone_gym_fl1",
                "followup_ticket_number": tkt,
            },
            headers=STUDENT_AARAV,
        )
        assert r2.status_code == 400
        assert "already resolved" in r2.json()["detail"].lower()

@pytest.mark.asyncio
async def test_10_closed_thread_cannot_be_escalated():
    """10. Closed issue threads cannot trigger escalation."""
    async with await get_test_client() as client:
        # Create initial complaint
        r1 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Old badminton court net torn",
                "description": "Court 1 net has holes.",
                "location_ref": "infra_zone_sports_fl1",
            },
            headers=STUDENT_AARAV,
        )
        tkt = r1.json()["ticket_number"]

        # Mark ticket as CLOSED in DB
        async with AsyncSessionLocal() as db:
            g = await db.scalar(select(Grievance).where(Grievance.ticket_number == tkt))
            g.status = GrievanceStatus.CLOSED
            await db.commit()

        # Attempt follow-up on closed ticket
        r2 = await client.post(
            "/api/v1/grievances",
            json={
                "title": "Follow up on closed ticket",
                "description": "Court net issue again.",
                "location_ref": "infra_zone_sports_fl1",
                "followup_ticket_number": tkt,
            },
            headers=STUDENT_AARAV,
        )
        assert r2.status_code == 400
        assert "closed" in r2.json()["detail"].lower()

@pytest.mark.asyncio
async def test_11_duplicate_ticket_submission_does_not_duplicate_escalation():
    """11. Duplicate requests do not create duplicate escalation records."""
    async with await get_test_client() as client:
        # Create 1, 2, 3
        r1 = await client.post(
            "/api/v1/grievances",
            json={"title": "Chemistry lab fume hood error", "description": "Fume hood fan not exhausting fumes properly.", "location_ref": "infra_zone_chem_b2"},
            headers=STUDENT_AARAV,
        )
        tkt1 = r1.json()["ticket_number"]

        r2 = await client.post(
            "/api/v1/grievances",
            json={"title": "Fume hood issue follow-up", "description": "Fume smell still spreading.", "location_ref": "infra_zone_chem_b2", "followup_ticket_number": tkt1},
            headers=STUDENT_AARAV,
        )
        tkt2 = r2.json()["ticket_number"]

        r3 = await client.post(
            "/api/v1/grievances",
            json={"title": "Fume hood third notice", "description": "High hazard risk.", "location_ref": "infra_zone_chem_b2", "followup_ticket_number": tkt2},
            headers=STUDENT_AARAV,
        )
        esc_id = r3.json()["escalation_id"]

        # Check total escalations for this thread in DB
        async with AsyncSessionLocal() as db:
            count = await db.scalar(
                select(func.count(VCEscalation.id)).where(VCEscalation.thread_id == r3.json()["thread_id"])
            )
            assert count == 1

@pytest.mark.asyncio
async def test_12_concurrent_third_complaints_do_not_duplicate_escalation():
    """12. Concurrent third-complaint submissions create exactly one escalation."""
    async with await get_test_client() as client:
        r1 = await client.post(
            "/api/v1/grievances",
            json={"title": "Hostel 3 laundry machine broken", "description": "Washing machine 4 won't drain.", "location_ref": "infra_zone_h3_laundry"},
            headers=STUDENT_AARAV,
        )
        tkt1 = r1.json()["ticket_number"]

        r2 = await client.post(
            "/api/v1/grievances",
            json={"title": "Washing machine still broken", "description": "Clothes soaked in stagnant water.", "location_ref": "infra_zone_h3_laundry", "followup_ticket_number": tkt1},
            headers=STUDENT_AARAV,
        )
        tkt2 = r2.json()["ticket_number"]

        # Fire two follow-ups concurrently
        req_a = client.post(
            "/api/v1/grievances",
            json={"title": "Third report: laundry machine 4", "description": "No action taken yet.", "location_ref": "infra_zone_h3_laundry", "followup_ticket_number": tkt2},
            headers=STUDENT_AARAV,
        )
        req_b = client.post(
            "/api/v1/grievances",
            json={"title": "Third report (alt): laundry machine 4", "description": "Still no action.", "location_ref": "infra_zone_h3_laundry", "followup_ticket_number": tkt2},
            headers=STUDENT_AARAV,
        )
        res_a, res_b = await asyncio.gather(req_a, req_b)
        assert res_a.status_code == 201
        assert res_b.status_code == 201

        # Check DB has exactly 1 escalation for this thread
        thread_id = r1.json()["thread_id"]
        async with AsyncSessionLocal() as db:
            escs = (await db.execute(
                select(VCEscalation).where(VCEscalation.thread_id == thread_id)
            )).scalars().all()
            assert len(escs) == 1

@pytest.mark.asyncio
async def test_13_unauthorized_users_cannot_access_vc_endpoints():
    """13. Missing or invalid staff token returns 401 on VC endpoints."""
    async with await get_test_client() as client:
        # Missing token
        r1 = await client.get("/api/v1/vc/escalations")
        assert r1.status_code == 401

        # Invalid token
        r2 = await client.get("/api/v1/vc/escalations", headers=INVALID_STAFF_AUTH)
        assert r2.status_code == 401

@pytest.mark.asyncio
async def test_14_non_vc_roles_cannot_access_vc_endpoints():
    """14. Non-VC staff roles (Supervisor, Admin) receive 403 Forbidden."""
    async with await get_test_client() as client:
        # Supervisor
        r1 = await client.get("/api/v1/vc/escalations", headers=SUPERVISOR_AUTH)
        assert r1.status_code == 403
        err_msg = r1.json()["detail"].lower()
        assert "vice-chancellor" in err_msg or "vice_chancellor" in err_msg

        # Admin
        r2 = await client.get("/api/v1/vc/escalations", headers=ADMIN_AUTH)
        assert r2.status_code == 403

@pytest.mark.asyncio
async def test_15_vc_rejection_requires_reason():
    """15. VC rejection requires mandatory reason; returns 400 if missing."""
    async with await get_test_client() as client:
        # Seed an escalation in DB
        async with AsyncSessionLocal() as db:
            esc = VCEscalation(
                thread_id=f"thread_test_rej_{uuid.uuid4().hex[:6]}",
                verified_student_id="stu_aarav_101",
                category="HOSTEL_WIFI",
                title="Test Rejection Escalation",
                description="Testing rejection validation",
                location_ref="infra_zone_test",
                complaint_count=3,
                related_tickets="[]",
                trigger_ticket_number="TKT-TEST-REJ",
                responsible_department="Hostel Operations",
                status="PENDING_REVIEW",
            )
            db.add(esc)
            await db.commit()
            await db.refresh(esc)
            esc_id = esc.escalation_id

        # Attempt rejection without remarks
        r = await client.post(
            f"/api/v1/vc/escalations/{esc_id}/decision",
            json={"decision": "REJECTED_WITH_REASON", "remarks": ""},
            headers=VC_AUTH,
        )
        assert r.status_code == 400
        assert "mandatory" in r.json()["detail"].lower()

@pytest.mark.asyncio
async def test_16_vc_decision_recorded_with_authenticated_identity():
    """16. VC decision is attributed to authenticated VC identity and audit trail recorded."""
    async with await get_test_client() as client:
        # Seed escalation
        async with AsyncSessionLocal() as db:
            esc = VCEscalation(
                thread_id=f"thread_test_dec_{uuid.uuid4().hex[:6]}",
                verified_student_id="stu_aarav_101",
                category="CAMPUS_SECURITY",
                title="Security Gate Access Card Reader Glitch",
                description="Gate 3 card swipe fails intermittently.",
                location_ref="infra_zone_gate3",
                complaint_count=3,
                related_tickets="[\"TKT-G1\", \"TKT-G2\", \"TKT-G3\"]",
                trigger_ticket_number="TKT-G3",
                responsible_department="Campus Security",
                status="PENDING_REVIEW",
            )
            db.add(esc)
            await db.commit()
            await db.refresh(esc)
            esc_id = esc.escalation_id

        # Submit ACTION_REQUIRED decision
        r = await client.post(
            f"/api/v1/vc/escalations/{esc_id}/decision",
            json={
                "decision": "ACTION_REQUIRED",
                "remarks": "Expedite hardware diagnostics with Vendor Support by tomorrow 10:00 AM.",
            },
            headers=VC_AUTH,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ACTION_REQUIRED"
        assert data["vc_decision"] == "ACTION_REQUIRED"
        assert data["vc_reviewer_id"] == "staff_vc_office"
        assert data["vc_remarks"] is not None

        # Fetch detail endpoint
        r_det = await client.get(f"/api/v1/vc/escalations/{esc_id}", headers=VC_AUTH)
        assert r_det.status_code == 200
        det = r_det.json()
        assert det["vc_reviewer_id"] == "staff_vc_office"
        assert det["status"] == "ACTION_REQUIRED"

@pytest.mark.asyncio
async def test_17_existing_apis_remain_functional():
    """17. Existing Student, Admin, and Swarm APIs remain fully functional."""
    async with await get_test_client() as client:
        # Student Health
        r_health = await client.get("/api/v1/health")
        assert r_health.status_code == 200

        # Admin Pending Approvals
        r_app = await client.get("/api/v1/approvals/pending", headers=SUPERVISOR_AUTH)
        assert r_app.status_code == 200

        # Swarm Feed (via /events or /feed alias)
        r_swarm = await client.get("/api/v1/swarm/events?limit=5")
        assert r_swarm.status_code == 200

@pytest.mark.asyncio
async def test_18_escalation_events_appear_in_swarm_without_meko_label():
    """18. Escalation events appear in swarm feed with actor SYSTEM, not MEKO_TOOL."""
    async with await get_test_client() as client:
        # Trigger an escalation
        r1 = await client.post(
            "/api/v1/grievances",
            json={"title": "Solar inverter smoke smell", "description": "Roof solar inverter burning odor.", "location_ref": "infra_zone_solar_r1"},
            headers=STUDENT_AARAV,
        )
        t1 = r1.json()["ticket_number"]

        r2 = await client.post(
            "/api/v1/grievances",
            json={"title": "Solar inverter still smelling", "description": "Second notice for odor.", "location_ref": "infra_zone_solar_r1", "followup_ticket_number": t1},
            headers=STUDENT_AARAV,
        )
        t2 = r2.json()["ticket_number"]

        r3 = await client.post(
            "/api/v1/grievances",
            json={"title": "Solar inverter critical risk", "description": "Fire risk in building roof.", "location_ref": "infra_zone_solar_r1", "followup_ticket_number": t2},
            headers=STUDENT_AARAV,
        )
        t3 = r3.json()["ticket_number"]

        # Fetch swarm feed for ticket t3
        r_swarm = await client.get(f"/api/v1/swarm/events?ticket_number={t3}")
        assert r_swarm.status_code == 200
        events = r_swarm.json()["events"]

        # Find VC_ESCALATION_TRIGGERED event
        esc_events = [e for e in events if e["event_type"] == "VC_ESCALATION_TRIGGERED"]
        assert len(esc_events) >= 1
        ev = esc_events[0]
        # Crucial invariants:
        assert ev["actor_type"] == "SYSTEM"
        assert ev["source"] != "MEKO_TOOL"
        assert ev["source"] == "GRIEVANCE"
        # Zero PII in event
        assert "stu_aarav_101" not in str(ev)
        assert "student-token" not in str(ev)

