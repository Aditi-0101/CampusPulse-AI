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

# Standard demo authentication test headers
AUTH_SUPERVISOR = {"X-Staff-Token": "staff-token-sharma-9102"}
AUTH_ADMIN = {"X-Staff-Token": "staff-token-patel-8431"}
AUTH_ADMIN_1 = {"X-Staff-Token": "staff-token-admin-5555"}
AUTH_NOC_MGR = {"X-Staff-Token": "staff-token-noc-mgr-7777"}
AUTH_READONLY = {"X-Staff-Token": "staff-token-readonly-1001"}
AUTH_AI_FORBIDDEN = {"X-Staff-Token": "staff-token-ai-forbidden"}
INVALID_AUTH = {"X-Staff-Token": "invalid-token-xyz-0000"}

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()

async def create_pending_grievance(title: str = "Test Outage") -> Grievance:
    """Helper to seed a grievance in PENDING_APPROVAL status."""
    async with AsyncSessionLocal() as db:
        tkt = f"TKT-APPR-{uuid.uuid4().hex[:6].upper()}"
        grievance = Grievance(
            ticket_number=tkt,
            student_anon_id="student_anon_user",
            location_ref="infra_zone_h3_fl2",
            title=title,
            description="Under-voltage hardware failure detected on corridor AP-H3.",
            category=GrievanceCategory.HOSTEL_WIFI,
            urgency="HIGH",
            status=GrievanceStatus.PENDING_APPROVAL,
            recommended_department="Network Infrastructure Engineering (Specialized NOC)",
            recommended_sla_hours=4,
            ai_recommendation="Escalated: PoE hardware defect requires physical replacement.",
            requires_human_approval=True,
            escalation_reason="Physical hardware replacement requires authorized human staff review.",
        )
        db.add(grievance)
        await db.commit()
        await db.refresh(grievance)
        return grievance

@pytest.mark.asyncio
async def test_successful_human_approval():
    """1. Successful human staff approval of a pending grievance recommendation using valid token."""
    grievance = await create_pending_grievance("Wi-Fi AP PoE failure")
    
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "decision": "APPROVED",
            "reason": "Verified diagnostic log against switch port telemetry; approved for physical technician dispatch.",
            "assigned_technician": "tech_lead_verma"
        }
        res = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json=payload,
            headers=AUTH_SUPERVISOR
        )
        assert res.status_code == 200
        data = res.json()

        assert data["ticket_number"] == grievance.ticket_number
        assert data["decision"] == "APPROVED"
        assert data["previous_status"] == "PENDING_APPROVAL"
        assert data["new_status"] == "APPROVED"
        assert data["reviewer_id"] == "staff_supervisor_sharma"
        assert data["reviewer_role"] == "NOC_SUPERVISOR"
        assert data["assigned_technician"] == "tech_lead_verma"
        assert data["is_spending_authorized"] is False

    # Verify DB persistence
    async with AsyncSessionLocal() as db:
        updated = await db.scalar(select(Grievance).where(Grievance.id == grievance.id))
        assert updated.status == GrievanceStatus.APPROVED

        approval_rec = await db.scalar(select(HumanApproval).where(HumanApproval.grievance_id == grievance.id))
        assert approval_rec is not None
        assert approval_rec.decision == "APPROVED"
        assert approval_rec.reviewer_id == "staff_supervisor_sharma"
        assert approval_rec.reviewer_role == "NOC_SUPERVISOR"
        assert approval_rec.budget_authorized == 0.0
        assert "poe hardware defect" in approval_rec.recommendation_snapshot.lower()
        print(f"\n[PASS] Human Approval Successful: Ticket={grievance.ticket_number}, Status={updated.status.value}")

@pytest.mark.asyncio
async def test_successful_human_rejection_with_reason():
    """2. Successful human staff rejection of a recommendation with mandatory reason."""
    grievance = await create_pending_grievance("Questionable AP Replacement")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "decision": "REJECTED",
            "reason": "Physical replacement rejected. Instructing remote firmware rollback and port power cycle first."
        }
        res = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json=payload,
            headers=AUTH_ADMIN
        )
        assert res.status_code == 200
        data = res.json()

        assert data["decision"] == "REJECTED"
        assert data["new_status"] == "REJECTED"
        assert data["reviewer_id"] == "staff_lead_patel"
        assert data["reviewer_role"] == "CAMPUS_ADMIN"
        assert "firmware rollback" in data["reason"].lower()

    # Verify DB persistence
    async with AsyncSessionLocal() as db:
        updated = await db.scalar(select(Grievance).where(Grievance.id == grievance.id))
        assert updated.status == GrievanceStatus.REJECTED
        print(f"[PASS] Human Rejection with Reason Successful: Ticket={grievance.ticket_number}, Status={updated.status.value}")

@pytest.mark.asyncio
async def test_rejection_without_reason_fails():
    """3. Rejection without a non-empty reason is rejected with HTTP 400."""
    grievance = await create_pending_grievance("Missing Rejection Reason Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Empty string
        res = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={
                "decision": "REJECTED",
                "reason": "   "
            },
            headers=AUTH_ADMIN
        )
        assert res.status_code == 400
        assert "non-empty justification reason" in res.json()["detail"].lower()

        # None/Missing reason
        res_none = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={
                "decision": "REJECTED"
            },
            headers=AUTH_ADMIN
        )
        assert res_none.status_code == 400
        print("[PASS] Rejection without reason properly rejected with HTTP 400.")

@pytest.mark.asyncio
async def test_approval_of_nonexistent_ticket_returns_404():
    """4. Approval attempt for nonexistent ticket returns HTTP 404."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "decision": "APPROVED",
            "reason": "Valid reason"
        }
        res = await client.post(
            "/api/v1/approvals/TKT-DOES-NOT-EXIST-999/decision",
            json=payload,
            headers=AUTH_ADMIN
        )
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
        print("[PASS] Nonexistent ticket correctly returns HTTP 404.")

@pytest.mark.asyncio
async def test_duplicate_approval_attempt_returns_409():
    """5. Duplicate approval attempts on an already decided ticket return HTTP 409 Conflict."""
    grievance = await create_pending_grievance("Duplicate Approval Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "decision": "APPROVED",
            "reason": "First approval sign-off"
        }
        # First decision succeeds
        res1 = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json=payload,
            headers=AUTH_ADMIN_1
        )
        assert res1.status_code == 200

        # Duplicate decision fails with 409 Conflict
        res2 = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json=payload,
            headers=AUTH_ADMIN_1
        )
        assert res2.status_code == 409
        assert "not pending approval" in res2.json()["detail"].lower() or "already" in res2.json()["detail"].lower()
        print("[PASS] Duplicate approval properly prevented with HTTP 409 Conflict.")

@pytest.mark.asyncio
async def test_rejection_after_approval_returns_409():
    """6. Attempting to reject an already approved ticket returns HTTP 409 Conflict."""
    grievance = await create_pending_grievance("Conflicting Rejection Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Approve
        res_appr = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={
                "decision": "APPROVED",
                "reason": "Operational signoff"
            },
            headers=AUTH_ADMIN_1
        )
        assert res_appr.status_code == 200

        # Step 2: Attempt conflicting rejection
        res_rej = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={
                "decision": "REJECTED",
                "reason": "Conflicting decision should be rejected"
            },
            headers=AUTH_ADMIN
        )
        assert res_rej.status_code == 409
        print("[PASS] Conflicting rejection after approval properly blocked with HTTP 409.")

@pytest.mark.asyncio
async def test_approval_does_not_authorize_spending():
    """7. Financial safety invariant: Human approval does NOT authorize spending or disburse funds."""
    grievance = await create_pending_grievance("Financial Safety Invariant Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={
                "decision": "APPROVED",
                "reason": "Operational NOC technician sign-off"
            },
            headers=AUTH_NOC_MGR
        )
        assert res.status_code == 200
        data = res.json()

        assert data["is_spending_authorized"] is False
        assert "purchasing" in data["financial_disclaimer"].lower() or "disbursement" in data["financial_disclaimer"].lower()

    async with AsyncSessionLocal() as db:
        approval_rec = await db.scalar(select(HumanApproval).where(HumanApproval.grievance_id == grievance.id))
        assert approval_rec.budget_authorized == 0.0
        print("[PASS] Verified: Human approval authorizes operational dispatch only, NOT spending.")

@pytest.mark.asyncio
async def test_missing_staff_token_returns_401():
    """8. Security check: Missing X-Staff-Token header is rejected with HTTP 401."""
    grievance = await create_pending_grievance("Unauthenticated Request Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Decision attempt without token
        res_dec = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={"decision": "APPROVED", "reason": "No token provided"}
        )
        assert res_dec.status_code == 401
        assert "missing 'x-staff-token' header" in res_dec.json()["detail"].lower()

        # Queue inspection without token
        res_queue = await client.get("/api/v1/approvals/pending")
        assert res_queue.status_code == 401
        print("[PASS] Missing X-Staff-Token properly rejected with HTTP 401.")

@pytest.mark.asyncio
async def test_invalid_staff_token_returns_401():
    """9. Security check: Invalid or forged X-Staff-Token is rejected with HTTP 401."""
    grievance = await create_pending_grievance("Invalid Token Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={"decision": "APPROVED", "reason": "Forged token test"},
            headers=INVALID_AUTH
        )
        assert res.status_code == 401
        assert "invalid or unrecognized staff token" in res.json()["detail"].lower()
        print("[PASS] Invalid X-Staff-Token properly rejected with HTTP 401.")

@pytest.mark.asyncio
async def test_forged_reviewer_in_body_cannot_impersonate():
    """10. Security check: Forged reviewer_id/reviewer_role in payload body is ignored; identity is resolved from token."""
    grievance = await create_pending_grievance("Impersonation Attack Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Caller supplies supervisor token, but passes forged dean/admin identity in request body
        payload = {
            "reviewer_id": "dr_patel_campus_dean",
            "reviewer_role": "CAMPUS_ADMIN",
            "decision": "APPROVED",
            "reason": "Attempting payload identity spoofing"
        }
        res = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json=payload,
            headers=AUTH_SUPERVISOR  # Maps server-side to staff_supervisor_sharma / NOC_SUPERVISOR
        )
        assert res.status_code == 200
        data = res.json()

        # Verified: Server resolved reviewer identity strictly from token, ignoring body
        assert data["reviewer_id"] == "staff_supervisor_sharma"
        assert data["reviewer_role"] == "NOC_SUPERVISOR"
        assert data["reviewer_id"] != "dr_patel_campus_dean"

    async with AsyncSessionLocal() as db:
        approval_rec = await db.scalar(select(HumanApproval).where(HumanApproval.grievance_id == grievance.id))
        assert approval_rec.reviewer_id == "staff_supervisor_sharma"
        assert approval_rec.reviewer_role == "NOC_SUPERVISOR"
        print("[PASS] Body impersonation prevented: Reviewer identity strictly derived from token.")

@pytest.mark.asyncio
async def test_unauthorized_role_cannot_perform_approval():
    """11. RBAC check: Unauthorized roles (e.g. READ_ONLY) are rejected with HTTP 403."""
    grievance = await create_pending_grievance("Unauthorized Role Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "decision": "APPROVED",
            "reason": "Read-only intern attempting approval"
        }
        res = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json=payload,
            headers=AUTH_READONLY  # Maps to staff_intern_verma / READ_ONLY
        )
        assert res.status_code == 403
        assert "does not have permission" in res.json()["detail"].lower()

    async with AsyncSessionLocal() as db:
        updated = await db.scalar(select(Grievance).where(Grievance.id == grievance.id))
        assert updated.status == GrievanceStatus.PENDING_APPROVAL  # Grievance remains untouched
        print("[PASS] RBAC enforced: Unauthorized role strictly blocked from approval (HTTP 403).")

@pytest.mark.asyncio
async def test_ai_agent_cannot_approve_recommendation():
    """12. Security check: AI agents cannot approve recommendations (via token or via payload)."""
    grievance = await create_pending_grievance("AI Self-Approval Attack Test")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Case A: AI agent using its own token mapping
        res1 = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={
                "decision": "APPROVED",
                "reason": "AI automated self approval attempt"
            },
            headers=AUTH_AI_FORBIDDEN
        )
        assert res1.status_code == 403
        assert "strictly forbidden" in res1.json()["detail"].lower()

        # Case B: Attempting to pass AI agent identifier in request body
        res2 = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={
                "reviewer_id": "frontdesk",
                "reviewer_role": "frontdesk_agent",
                "decision": "APPROVED",
                "reason": "AI automated self approval attempt"
            },
            headers=AUTH_SUPERVISOR
        )
        assert res2.status_code == 403

        # Case C: Coding agent in request body
        res3 = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={
                "reviewer_id": "coding_agent",
                "reviewer_role": "developer",
                "decision": "APPROVED",
                "reason": "AI developer self approval"
            },
            headers=AUTH_SUPERVISOR
        )
        assert res3.status_code == 403
        print("[PASS] Security invariant enforced: AI agents strictly blocked from self-approving (HTTP 403).")

@pytest.mark.asyncio
async def test_existing_grievance_workflow_remains_intact():
    """13. End-to-end integration: Grievance submission flows into pending approvals queue."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Submit new grievance
        payload = {
            "title": "Wi-Fi AP power fault in hostel corridor",
            "description": "Total loss of Wi-Fi in corridor due to power unit malfunction.",
            "student_anon_id": "student_anon_user",
            "location_ref": "infra_zone_h3_fl2",
            "category": "HOSTEL_WIFI"
        }
        res_create = await client.post("/api/v1/grievances", json=payload)
        assert res_create.status_code == 201
        created = res_create.json()
        ticket_number = created["ticket_number"]

        # Retrieve pending approvals list with authenticated staff token
        res_pending = await client.get("/api/v1/approvals/pending", headers=AUTH_SUPERVISOR)
        assert res_pending.status_code == 200
        pending_list = res_pending.json()

        # If it required human approval, verify it appears in pending queue
        if created.get("requires_human_approval"):
            matching = [item for item in pending_list if item["ticket_number"] == ticket_number]
            assert len(matching) == 1
            assert matching[0]["status"] == "PENDING_APPROVAL"
            print(f"[PASS] Workflow Intact: Ticket {ticket_number} successfully registered in pending approvals queue.")
        else:
            print(f"[PASS] Workflow Intact: Routine Ticket {ticket_number} triaged without pending escalation.")

@pytest.mark.asyncio
async def test_generic_approval_route_missing_token_returns_401():
    """14. Generic route check: POST /api/v1/approvals/decision without token returns HTTP 401."""
    grievance = await create_pending_grievance("Generic Route Missing Token Test")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "ticket_number": grievance.ticket_number,
            "decision": "APPROVED",
            "reason": "Missing token on generic endpoint"
        }
        res = await client.post("/api/v1/approvals/decision", json=payload)
        assert res.status_code == 401
        assert "missing 'x-staff-token' header" in res.json()["detail"].lower()
        print("[PASS] Generic route properly rejects missing token with HTTP 401.")

@pytest.mark.asyncio
async def test_generic_approval_route_invalid_token_returns_401():
    """15. Generic route check: POST /api/v1/approvals/decision with invalid token returns HTTP 401."""
    grievance = await create_pending_grievance("Generic Route Invalid Token Test")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "ticket_number": grievance.ticket_number,
            "decision": "APPROVED",
            "reason": "Invalid token on generic endpoint"
        }
        res = await client.post("/api/v1/approvals/decision", json=payload, headers=INVALID_AUTH)
        assert res.status_code == 401
        assert "invalid or unrecognized staff token" in res.json()["detail"].lower()
        print("[PASS] Generic route properly rejects invalid token with HTTP 401.")

@pytest.mark.asyncio
async def test_generic_approval_route_readonly_returns_403():
    """16. Generic route check: POST /api/v1/approvals/decision with READ_ONLY token returns HTTP 403."""
    grievance = await create_pending_grievance("Generic Route Readonly Test")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "ticket_number": grievance.ticket_number,
            "decision": "APPROVED",
            "reason": "Readonly token on generic endpoint"
        }
        res = await client.post("/api/v1/approvals/decision", json=payload, headers=AUTH_READONLY)
        assert res.status_code == 403
        assert "does not have permission" in res.json()["detail"].lower()
        print("[PASS] Generic route properly rejects READ_ONLY role with HTTP 403.")

@pytest.mark.asyncio
async def test_generic_approval_route_authorized_decision_succeeds():
    """17. Generic route check: Authorized role can approve via POST /api/v1/approvals/decision."""
    grievance = await create_pending_grievance("Generic Route Authorized Test")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "ticket_number": grievance.ticket_number,
            "decision": "APPROVED",
            "reason": "Authorized decision via generic route",
            "assigned_technician": "tech_lead_shukla"
        }
        res = await client.post("/api/v1/approvals/decision", json=payload, headers=AUTH_SUPERVISOR)
        assert res.status_code == 200
        data = res.json()
        assert data["ticket_number"] == grievance.ticket_number
        assert data["decision"] == "APPROVED"
        assert data["reviewer_id"] == "staff_supervisor_sharma"
        assert data["reviewer_role"] == "NOC_SUPERVISOR"
        assert data["is_spending_authorized"] is False

    async with AsyncSessionLocal() as db:
        updated = await db.scalar(select(Grievance).where(Grievance.id == grievance.id))
        assert updated.status == GrievanceStatus.APPROVED
        rec = await db.scalar(select(HumanApproval).where(HumanApproval.grievance_id == grievance.id))
        assert rec is not None
        assert rec.budget_authorized == 0.0
        print("[PASS] Generic route authorized decision succeeds with budget_authorized=0.0.")

@pytest.mark.asyncio
async def test_whitespace_only_staff_token_returns_401():
    """18. Security check: Whitespace-only X-Staff-Token returns HTTP 401."""
    grievance = await create_pending_grievance("Whitespace Token Test")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/approvals/{grievance.ticket_number}/decision",
            json={"decision": "APPROVED", "reason": "Whitespace token attempt"},
            headers={"X-Staff-Token": "    "}
        )
        assert res.status_code == 401
        assert "missing 'x-staff-token' header" in res.json()["detail"].lower()
        print("[PASS] Whitespace-only X-Staff-Token properly rejected with HTTP 401.")

@pytest.mark.asyncio
async def test_case_insensitive_staff_role_normalization_and_rbac():
    """19. Security check: Lowercase or mixed-case configured roles normalize correctly and enforce RBAC."""
    from backend.app.core.auth import parse_staff_token_map, verify_approval_permission, StaffIdentity
    
    # Delimited format with mixed and lowercase roles
    config_delim = "tkn_noc_lower:staff_1:noc_supervisor,tkn_admin_mixed:staff_2:CaMpUs_AdMiN,tkn_ro_lower:staff_3:read_only"
    parsed_map = parse_staff_token_map(config_delim)
    
    assert parsed_map["tkn_noc_lower"].reviewer_role == "NOC_SUPERVISOR"
    assert parsed_map["tkn_admin_mixed"].reviewer_role == "CAMPUS_ADMIN"
    assert parsed_map["tkn_ro_lower"].reviewer_role == "READ_ONLY"

    # JSON format with lowercase role
    config_json = '{"tkn_json_noc": {"reviewer_id": "staff_4", "reviewer_role": "noc_supervisor"}}'
    parsed_json_map = parse_staff_token_map(config_json)
    assert parsed_json_map["tkn_json_noc"].reviewer_role == "NOC_SUPERVISOR"

    # RBAC verification on un-normalized StaffIdentity object
    unnormalized_authorized = StaffIdentity(reviewer_id="staff_test", reviewer_role="noc_supervisor")
    verify_approval_permission(unnormalized_authorized)  # Must not raise

    unnormalized_unauthorized = StaffIdentity(reviewer_id="staff_ro", reviewer_role="read_only")
    with pytest.raises(Exception) as excinfo:
        verify_approval_permission(unnormalized_unauthorized)
    assert excinfo.value.status_code == 403
    print("[PASS] Case-insensitive role normalization and RBAC verification confirmed.")

if __name__ == "__main__":
    asyncio.run(test_successful_human_approval())
    asyncio.run(test_successful_human_rejection_with_reason())
    asyncio.run(test_rejection_without_reason_fails())
    asyncio.run(test_approval_of_nonexistent_ticket_returns_404())
    asyncio.run(test_duplicate_approval_attempt_returns_409())
    asyncio.run(test_rejection_after_approval_returns_409())
    asyncio.run(test_approval_does_not_authorize_spending())
    asyncio.run(test_missing_staff_token_returns_401())
    asyncio.run(test_invalid_staff_token_returns_401())
    asyncio.run(test_forged_reviewer_in_body_cannot_impersonate())
    asyncio.run(test_unauthorized_role_cannot_perform_approval())
    asyncio.run(test_ai_agent_cannot_approve_recommendation())
    asyncio.run(test_existing_grievance_workflow_remains_intact())
    asyncio.run(test_generic_approval_route_missing_token_returns_401())
    asyncio.run(test_generic_approval_route_invalid_token_returns_401())
    asyncio.run(test_generic_approval_route_readonly_returns_403())
    asyncio.run(test_generic_approval_route_authorized_decision_succeeds())
    asyncio.run(test_whitespace_only_staff_token_returns_401())
    asyncio.run(test_case_insensitive_staff_role_normalization_and_rbac())
    print("\n=== All Stage D Approval and Authentication Tests Passed Successfully ===")

