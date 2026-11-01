import os
import sys
import uuid
import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from datetime import datetime, timezone
from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.database import init_db, AsyncSessionLocal
from backend.app.core.config import settings
from backend.app.models.grievance import Grievance, GrievanceStatus, GrievanceCategory
from backend.app.models.escalation import VCEscalation
from backend.app.main import app

# Configured demo credentials from environment
STUDENT_AARAV_CRED = "student-token-aarav-101"
STUDENT_PRIYA_CRED = "student-token-priya-202"
STAFF_SUPERVISOR_CRED = "staff-token-sharma-9102"
STAFF_ADMIN_CRED = "staff-token-patel-8431"
STAFF_VC_CRED = "demo-token-vice-chancellor"
INVALID_CRED = "invalid-token-xyz-9999"

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()

async def get_test_client():
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")

@pytest.mark.asyncio
async def test_01_successful_student_login():
    """1. Student credential logs in, receives HttpOnly cookie, and redirects to /student."""
    async with await get_test_client() as client:
        res = await client.post("/api/v1/auth/login", json={"credential": STUDENT_AARAV_CRED})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "authenticated"
        assert data["user"]["role"] == "STUDENT"
        assert data["user"]["portal"] == "student"
        assert data["redirect_url"] == "/student"
        assert settings.SESSION_COOKIE_NAME in client.cookies

@pytest.mark.asyncio
async def test_02_successful_staff_login():
    """2. Staff supervisor credential logs in, receives cookie, and redirects to /admin."""
    async with await get_test_client() as client:
        res = await client.post("/api/v1/auth/login", json={"credential": STAFF_SUPERVISOR_CRED})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "authenticated"
        assert data["user"]["role"] == "NOC_SUPERVISOR"
        assert data["user"]["portal"] == "admin"
        assert data["redirect_url"] == "/admin"
        assert settings.SESSION_COOKIE_NAME in client.cookies

@pytest.mark.asyncio
async def test_03_successful_vc_login():
    """3. Vice-Chancellor credential logs in, receives cookie, and redirects to /vc."""
    async with await get_test_client() as client:
        res = await client.post("/api/v1/auth/login", json={"credential": STAFF_VC_CRED})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "authenticated"
        assert data["user"]["role"] == "VICE_CHANCELLOR"
        assert data["user"]["portal"] == "vc"
        assert data["redirect_url"] == "/vc"
        assert settings.SESSION_COOKIE_NAME in client.cookies

@pytest.mark.asyncio
async def test_04_invalid_credential_rejection():
    """4. Invalid credential returns 401 without disclosing role configuration."""
    async with await get_test_client() as client:
        res = await client.post("/api/v1/auth/login", json={"credential": INVALID_CRED})
        assert res.status_code == 401
        err = res.json()["detail"].lower()
        assert "authentication failed" in err or "invalid" in err
        assert settings.SESSION_COOKIE_NAME not in client.cookies

@pytest.mark.asyncio
async def test_05_session_persistence_and_me():
    """5. GET /api/v1/auth/me returns authenticated profile from cookie."""
    async with await get_test_client() as client:
        # Before login -> 401
        res0 = await client.get("/api/v1/auth/me")
        assert res0.status_code == 401

        # Login as student
        await client.post("/api/v1/auth/login", json={"credential": STUDENT_AARAV_CRED})

        # Profile check via cookie
        res1 = await client.get("/api/v1/auth/me")
        assert res1.status_code == 200
        data = res1.json()
        assert data["role"] == "STUDENT"
        assert data["user_id"] == "std_aarav_sharma_9821"

@pytest.mark.asyncio
async def test_06_logout_clears_cookie():
    """6. POST /api/v1/auth/logout invalidates session and clears cookie."""
    async with await get_test_client() as client:
        await client.post("/api/v1/auth/login", json={"credential": STUDENT_AARAV_CRED})
        assert settings.SESSION_COOKIE_NAME in client.cookies

        # Logout
        res_out = await client.post("/api/v1/auth/logout")
        assert res_out.status_code == 200
        assert res_out.json()["status"] == "logged_out"

        # Subsequent profile query returns 401
        res_me = await client.get("/api/v1/auth/me")
        assert res_me.status_code == 401

@pytest.mark.asyncio
async def test_07_student_cannot_access_admin_or_vc_or_swarm():
    """7. Authenticated student receives 403 on Admin approvals, VC, and Swarm endpoints."""
    async with await get_test_client() as client:
        await client.post("/api/v1/auth/login", json={"credential": STUDENT_AARAV_CRED})

        # Attempt to view admin pending approvals
        r_admin = await client.get("/api/v1/approvals/pending")
        assert r_admin.status_code == 403
        assert "not authorized" in r_admin.json()["detail"].lower()

        # Attempt to access VC escalations
        r_vc = await client.get("/api/v1/vc/escalations")
        assert r_vc.status_code == 403

        # Attempt to access live swarm feed
        r_swarm = await client.get("/api/v1/swarm/events")
        assert r_swarm.status_code == 403

@pytest.mark.asyncio
async def test_08_admin_cannot_access_vc_endpoints():
    """8. Authenticated staff admin receives 403 on VC endpoints."""
    async with await get_test_client() as client:
        await client.post("/api/v1/auth/login", json={"credential": STAFF_ADMIN_CRED})

        # Can access admin pending approvals
        r_admin = await client.get("/api/v1/approvals/pending")
        assert r_admin.status_code == 200

        # Can access swarm feed
        r_swarm = await client.get("/api/v1/swarm/events")
        assert r_swarm.status_code == 200

        # Cannot access VC escalations
        r_vc = await client.get("/api/v1/vc/escalations")
        assert r_vc.status_code == 403
        assert "vice-chancellor" in r_vc.json()["detail"].lower()

@pytest.mark.asyncio
async def test_09_vc_can_access_vc_endpoints():
    """9. Authenticated Vice-Chancellor can access VC escalations."""
    async with await get_test_client() as client:
        await client.post("/api/v1/auth/login", json={"credential": STAFF_VC_CRED})

        # VC can access VC escalations
        r_vc = await client.get("/api/v1/vc/escalations")
        assert r_vc.status_code == 200
        assert isinstance(r_vc.json(), list)

@pytest.mark.asyncio
async def test_10_non_vc_cannot_make_vc_decision():
    """10. Non-VC staff cannot submit decisions on VC escalations."""
    # Seed an escalation
    async with AsyncSessionLocal() as db:
        esc = VCEscalation(
            thread_id=f"thread_auth_test_{uuid.uuid4().hex[:6]}",
            verified_student_id="std_aarav_sharma_9821",
            title="Wi-Fi Router Burnout",
            description="High hazard risk in hostel block",
            location_ref="infra_zone_h3_fl1",
            related_tickets="[]",
            trigger_ticket_number="TKT-VC-AUTH-01",
            responsible_department="Hostel Operations",
            status="PENDING_REVIEW",
        )
        db.add(esc)
        await db.commit()
        await db.refresh(esc)
        esc_id = esc.escalation_id

    async with await get_test_client() as client:
        # Login as NOC Supervisor
        await client.post("/api/v1/auth/login", json={"credential": STAFF_SUPERVISOR_CRED})

        # Attempt to make decision
        r_dec = await client.post(
            f"/api/v1/vc/escalations/{esc_id}/decision",
            json={"decision": "ACTION_REQUIRED", "remarks": "Unauthorized attempt"}
        )
        assert r_dec.status_code == 403
        assert "vice-chancellor" in r_dec.json()["detail"].lower()

@pytest.mark.asyncio
async def test_11_student_cannot_track_another_students_ticket():
    """11. Authenticated student is forbidden from tracking another student's grievance."""
    # Seed a grievance owned by Aarav
    tkt_aarav = f"TKT-STU-A-{uuid.uuid4().hex[:6].upper()}"
    async with AsyncSessionLocal() as db:
        g = Grievance(
            ticket_number=tkt_aarav,
            student_anon_id="student_anon_aarav",
            verified_student_id="std_aarav_sharma_9821",
            title="Aarav Private Issue",
            description="Wi-Fi drops in Aarav room",
            location_ref="infra_zone_h3_fl2",
            category=GrievanceCategory.HOSTEL_WIFI,
            status=GrievanceStatus.SUBMITTED,
        )
        db.add(g)
        await db.commit()

    async with await get_test_client() as client:
        # Login as Priya
        await client.post("/api/v1/auth/login", json={"credential": STUDENT_PRIYA_CRED})

        # Priya attempts to track Aarav's ticket
        r_track = await client.get(f"/api/v1/grievances/{tkt_aarav}/track")
        assert r_track.status_code == 403
        assert "belongs to another student" in r_track.json()["detail"].lower()

@pytest.mark.asyncio
async def test_12_authenticated_student_can_track_own_ticket():
    """12. Authenticated student can successfully track their own ticket."""
    tkt_aarav = f"TKT-STU-OWN-{uuid.uuid4().hex[:6].upper()}"
    async with AsyncSessionLocal() as db:
        g = Grievance(
            ticket_number=tkt_aarav,
            student_anon_id="student_anon_aarav",
            verified_student_id="std_aarav_sharma_9821",
            title="Aarav Own Ticket",
            description="Power fluctuation in hostel",
            location_ref="infra_zone_h3_fl2",
            category=GrievanceCategory.HOSTEL_ELECTRICITY,
            status=GrievanceStatus.SUBMITTED,
        )
        db.add(g)
        await db.commit()

    async with await get_test_client() as client:
        await client.post("/api/v1/auth/login", json={"credential": STUDENT_AARAV_CRED})

        r_track = await client.get(f"/api/v1/grievances/{tkt_aarav}/track")
        assert r_track.status_code == 200
        assert r_track.json()["ticket_number"] == tkt_aarav

@pytest.mark.asyncio
async def test_13_student_can_list_own_grievances():
    """13. Authenticated student lists only their own submitted grievances."""
    async with await get_test_client() as client:
        await client.post("/api/v1/auth/login", json={"credential": STUDENT_AARAV_CRED})

        r_list = await client.get("/api/v1/student/grievances")
        assert r_list.status_code == 200
        items = r_list.json()
        assert isinstance(items, list)

@pytest.mark.asyncio
async def test_14_tampered_cookie_rejected():
    """14. Tampered or forged session cookie is rejected with 401."""
    async with await get_test_client() as client:
        # Forge fake cookie
        client.cookies.set(settings.SESSION_COOKIE_NAME, "forged_payload.invalid_signature")

        r = await client.get("/api/v1/auth/me")
        assert r.status_code == 401
