import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.database import init_db, AsyncSessionLocal
from backend.app.models.grievance import Grievance, GrievanceStatus, GrievanceCategory
from backend.app.models.approval import HumanApproval
from backend.app.models.meko_event import MekoEvent
from backend.app.main import app
from backend.app.services.swarm_service import (
    swarm_service,
    encode_cursor,
    decode_cursor,
)
from backend.app.schemas.swarm import SwarmActivityEvent

AUTH_SUPERVISOR = {"X-Staff-Token": "staff-token-sharma-9102"}
AUTH_READONLY = {"X-Staff-Token": "staff-token-readonly-1001"}

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    await init_db()


# =============================================================================
# Helper Seeding Fixtures
# =============================================================================

async def seed_isolated_swarm_scenario():
    """Seeds a controlled, isolated end-to-end swarm scenario for deterministic testing."""
    tkt = f"TKT-SWM-{uuid.uuid4().hex[:6].upper()}"
    conv_id = f"conv_swm_{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        # 1. Grievance
        g = Grievance(
            ticket_number=tkt,
            student_anon_id="student_anon_secret_id_44",
            location_ref="infra_zone_h3_fl2",
            title="Wi-Fi Drop near room 204",
            description="Continuous connection timeout observed on floor 2.",
            category=GrievanceCategory.HOSTEL_WIFI,
            urgency="HIGH",
            status=GrievanceStatus.APPROVED,
            conversation_id=conv_id,
            recommended_department="Network Infrastructure Engineering (Specialized NOC)",
            recommended_sla_hours=4,
            ai_recommendation="Escalated: PoE hardware defect requires physical replacement.",
            requires_human_approval=True,
            escalation_reason="Hardware defect requires human supervisor authorization.",
            meko_context_used=True,
            meko_context_summary="Retrieved PoE diagnostic history for zone infra_zone_h3_fl2.",
            created_at=datetime.utcnow() - timedelta(minutes=15),
        )
        db.add(g)
        await db.commit()
        await db.refresh(g)

        # 2. Meko Events
        # 2a. conversation_create (Front Desk)
        me1 = MekoEvent(
            grievance_id=g.id,
            agent_role="frontdesk",
            datapack_id="318fdc74-eb15-4cf4-9be5-57b5820b3264",
            tool_name="conversation_create",
            event_type="CONVERSATION_INIT",
            status="SUCCESS",
            arguments_json=json.dumps({"title": f"Intake: {tkt} (infra_zone_h3_fl2)", "agent_id": "product_agent:frontdesk"}),
            response_json=json.dumps({"id": conv_id, "agent_id": "product_agent:frontdesk"}),
            latency_ms=120.5,
            timestamp=datetime.utcnow() - timedelta(minutes=14),
        )
        # 2b. context_search (Front Desk - duplicate check)
        me2 = MekoEvent(
            grievance_id=g.id,
            agent_role="frontdesk",
            datapack_id="318fdc74-eb15-4cf4-9be5-57b5820b3264",
            tool_name="context_search",
            event_type="MEMORY_RECALLED",
            status="SUCCESS",
            arguments_json=json.dumps({"query": "Wi-Fi connectivity infra_zone_h3_fl2", "conversation_id": conv_id}),
            response_json=json.dumps({"results": {"memory": [{"id": "mem_1", "text": "Prior zone report"}]}}),
            latency_ms=450.2,
            timestamp=datetime.utcnow() - timedelta(minutes=13),
        )
        # 2c. context_search (Dispatch - hardware history)
        me3 = MekoEvent(
            grievance_id=g.id,
            agent_role="dispatch",
            datapack_id="cdb3987f-b677-495f-8d87-01999c3f9b91",
            tool_name="context_search",
            event_type="MEMORY_RECALLED",
            status="SUCCESS",
            arguments_json=json.dumps({"query": "Infrastructure hardware defect infra_zone_h3_fl2 AP-H3"}),
            response_json=json.dumps({"results": {"knowledge_base": [{"text": "PoE voltage drop documented."}]}}),
            latency_ms=620.0,
            timestamp=datetime.utcnow() - timedelta(minutes=10),
        )
        # 2d. failed context search to test error fidelity
        me4_failed = MekoEvent(
            grievance_id=g.id,
            agent_role="dispatch",
            datapack_id="cdb3987f-b677-495f-8d87-01999c3f9b91",
            tool_name="context_search",
            event_type="MEMORY_RECALLED",
            status="ERROR",
            arguments_json=json.dumps({"query": "invalid query simulation"}),
            response_json=json.dumps({"error": "Remote connection timeout to MCP endpoint", "is_error": True}),
            latency_ms=5000.0,
            timestamp=datetime.utcnow() - timedelta(minutes=8),
        )
        db.add_all([me1, me2, me3, me4_failed])
        await db.commit()

        # 3. Human Approval
        ha = HumanApproval(
            grievance_id=g.id,
            ticket_number=tkt,
            reviewer_id="staff_supervisor_sharma",
            reviewer_role="NOC_SUPERVISOR",
            decision="APPROVED",
            reason="Verified hardware fault in zone. Field dispatch authorized.",
            assigned_technician="Tech Lead Verma",
            budget_authorized=0.0,
            created_at=datetime.utcnow() - timedelta(minutes=5),
        )
        db.add(ha)
        await db.commit()

        return tkt, g.id, conv_id


# =============================================================================
# Unit & Integration Tests (15 Requirements)
# =============================================================================

@pytest.mark.asyncio
async def test_1_meko_event_normalization():
    """1. Verify normalization of Meko tool events into SwarmActivityEvent."""
    me = MekoEvent(
        id=9991,
        grievance_id=101,
        agent_role="frontdesk",
        datapack_id="318fdc74-eb15-4cf4-9be5-57b5820b3264",
        tool_name="context_search",
        event_type="MEMORY_RECALLED",
        status="SUCCESS",
        arguments_json=json.dumps({"query": "test query"}),
        response_json=json.dumps({"results": []}),
        latency_ms=234.56,
        timestamp=datetime(2026, 10, 31, 12, 0, 0),
    )
    norm = swarm_service.normalize_meko_event(me, ticket_number="TKT-TEST-001")
    assert norm.event_id == "meko_9991"
    assert norm.source == "MEKO_TOOL"
    assert norm.actor_type == "AGENT"
    assert norm.actor == "agent:frontdesk"
    assert norm.tool_name == "context_search"
    assert norm.datapack_id == "318fdc74-eb15-4cf4-9be5-57b5820b3264"
    assert norm.ticket_number == "TKT-TEST-001"
    assert norm.status == "SUCCESS"
    assert norm.latency_ms == 234.56
    assert norm.is_fallback is False
    assert "searched" in norm.summary.lower()


@pytest.mark.asyncio
async def test_2_human_approval_normalization_and_privacy():
    """2. Verify human approval event normalization: role exposed, reviewer_id NEVER exposed."""
    ha = HumanApproval(
        id=8881,
        grievance_id=102,
        ticket_number="TKT-TEST-002",
        reviewer_id="private_staff_id_sharma",
        reviewer_role="NOC_SUPERVISOR",
        decision="APPROVED",
        reason="Field inspection needed",
        assigned_technician="Tech Verma",
        budget_authorized=0.0,
        created_at=datetime(2026, 10, 31, 12, 10, 0),
    )
    norm = swarm_service.normalize_approval_event(ha)
    assert norm.event_id == "approval_8881"
    assert norm.source == "HUMAN_APPROVAL"
    assert norm.actor_type == "HUMAN"
    assert norm.actor == "staff:NOC_SUPERVISOR"
    assert "private_staff_id_sharma" not in norm.actor
    assert "private_staff_id_sharma" not in norm.summary
    assert norm.event_type == "DISPATCH_APPROVED"
    assert norm.status == "APPROVED"
    assert norm.tool_name is None
    assert norm.datapack_id is None
    assert norm.latency_ms is None
    assert norm.details.get("assigned_technician") == "Tech Verma"


@pytest.mark.asyncio
async def test_3_grievance_milestone_normalization():
    """3. Verify grievance lifecycle milestone normalization."""
    g = Grievance(
        id=7771,
        ticket_number="TKT-TEST-003",
        student_anon_id="student_anon_secret",
        location_ref="infra_zone_h3_fl2",
        title="Wi-Fi Flapping",
        description="Drops frequently",
        category=GrievanceCategory.HOSTEL_WIFI,
        urgency="HIGH",
        status=GrievanceStatus.PENDING_APPROVAL,
        requires_human_approval=True,
        recommended_department="Campus NOC",
        created_at=datetime(2026, 10, 31, 12, 0, 0),
    )
    milestones = swarm_service.normalize_grievance_milestones(g)
    types = [m.event_type for m in milestones]
    assert "GRIEVANCE_SUBMITTED" in types
    assert "TRIAGE_COMPLETED" in types
    assert "ESCALATED_FOR_APPROVAL" in types
    # Check stable IDs
    assert any(m.event_id == "grievance_7771_submitted" for m in milestones)
    assert any(m.event_id == "grievance_7771_triaged" for m in milestones)
    assert any(m.event_id == "grievance_7771_escalated" for m in milestones)


@pytest.mark.asyncio
async def test_4_chronological_ordering():
    """4. Feed returns events in strict chronological order."""
    tkt, _, _ = await seed_isolated_swarm_scenario()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get(f"/api/v1/swarm/events?ticket_number={tkt}")
        assert res.status_code == 200
        data = res.json()
        events = data["events"]
        assert len(events) >= 4

        # Verify ascending chronological sequence
        timestamps = [e["timestamp"] for e in events]
        for i in range(len(timestamps) - 1):
            assert timestamps[i] <= timestamps[i + 1]


@pytest.mark.asyncio
async def test_5_stable_ids_across_sources():
    """5. All events have non-colliding, stable prefixed IDs."""
    tkt, _, _ = await seed_isolated_swarm_scenario()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get(f"/api/v1/swarm/events?ticket_number={tkt}")
        assert res.status_code == 200
        events = res.json()["events"]

        prefixes = set(e["event_id"].split("_")[0] for e in events)
        assert "meko" in prefixes
        assert "approval" in prefixes
        assert "grievance" in prefixes

        ids = [e["event_id"] for e in events]
        assert len(ids) == len(set(ids)), "Collision detected in event IDs!"


@pytest.mark.asyncio
async def test_6_cursor_pagination_without_duplicates_or_skips():
    """6. Cursor pagination pages through events without duplicates or skips."""
    tkt, _, _ = await seed_isolated_swarm_scenario()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Fetch all events at once for ground truth
        full_res = await client.get(f"/api/v1/swarm/events?ticket_number={tkt}&limit=50")
        all_events = full_res.json()["events"]
        total_count = len(all_events)
        assert total_count >= 4

        # Page with limit=2
        paged_events = []
        next_cursor = None

        while True:
            url = f"/api/v1/swarm/events?ticket_number={tkt}&limit=2"
            if next_cursor:
                url += f"&cursor={next_cursor}"

            page_res = await client.get(url)
            assert page_res.status_code == 200
            page_data = page_res.json()
            paged_events.extend(page_data["events"])

            if not page_data["has_more"]:
                break
            next_cursor = page_data["next_cursor"]
            assert next_cursor is not None

        # Verify exact 1-to-1 match without duplicates or skips
        all_ids = [e["event_id"] for e in all_events]
        paged_ids = [e["event_id"] for e in paged_events]
        assert paged_ids == all_ids
        assert len(paged_ids) == len(set(paged_ids))


@pytest.mark.asyncio
async def test_7_ticket_filtering():
    """7. Ticket filter isolates events for only that ticket."""
    tkt1, _, _ = await seed_isolated_swarm_scenario()
    tkt2, _, _ = await seed_isolated_swarm_scenario()
    assert tkt1 != tkt2

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res1 = await client.get(f"/api/v1/swarm/events?ticket_number={tkt1}")
        assert res1.status_code == 200
        for ev in res1.json()["events"]:
            assert ev["ticket_number"] == tkt1

        res2 = await client.get(f"/api/v1/swarm/events?ticket_number={tkt2}")
        assert res2.status_code == 200
        for ev in res2.json()["events"]:
            assert ev["ticket_number"] == tkt2


@pytest.mark.asyncio
async def test_8_agent_filtering():
    """8. Agent role filter returns only events for the requested agent."""
    await seed_isolated_swarm_scenario()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res_fd = await client.get("/api/v1/swarm/events?agent_role=frontdesk")
        assert res_fd.status_code == 200
        for ev in res_fd.json()["events"]:
            if ev["source"] == "MEKO_TOOL":
                assert ev["actor"] == "agent:frontdesk"

        res_dp = await client.get("/api/v1/swarm/events?agent_role=dispatch")
        assert res_dp.status_code == 200
        for ev in res_dp.json()["events"]:
            if ev["source"] == "MEKO_TOOL":
                assert ev["actor"] == "agent:dispatch"


@pytest.mark.asyncio
async def test_9_metrics_accuracy():
    """9. Swarm metrics reflect actual database aggregates."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/api/v1/swarm/metrics")
        assert res.status_code == 200
        data = res.json()

        assert data["total_meko_tool_calls"] >= 4
        assert data["successful_calls"] >= 3
        assert data["failed_calls"] >= 1
        assert data["avg_latency_ms"] > 0
        assert data["context_searches_count"] >= 2
        assert data["human_approvals_count"] >= 1
        assert "frontdesk" in data["active_agent_roles"]
        assert "dispatch" in data["active_agent_roles"]
        assert "recent_metrics" in data
        assert data["recent_metrics"]["tool_calls"] >= 0


@pytest.mark.asyncio
async def test_10_replay_ordering_and_stage_detection():
    """10. Ticket replay ordering and completeness breakdown."""
    tkt, _, _ = await seed_isolated_swarm_scenario()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get(f"/api/v1/swarm/replay?ticket_number={tkt}")
        assert res.status_code == 200
        data = res.json()

        assert data["ticket_number"] == tkt
        assert "INTAKE_SUBMISSION" in data["available_stages"]
        assert "FRONTDESK_TRIAGE" in data["available_stages"]
        assert "MEKO_CONTEXT_SEARCH" in data["available_stages"]
        assert "HUMAN_STAFF_OVERSIGHT" in data["available_stages"]
        assert len(data["events"]) >= 4

        # Chronological order in replay
        timestamps = [e["timestamp"] for e in data["events"]]
        for i in range(len(timestamps) - 1):
            assert timestamps[i] <= timestamps[i + 1]

        # 404 on nonexistent ticket
        bad_res = await client.get("/api/v1/swarm/replay?ticket_number=TKT-NONEXISTENT")
        assert bad_res.status_code == 404


@pytest.mark.asyncio
async def test_11_sse_stream_format_and_catchup():
    """11. SSE stream returns text/event-stream with id, event, heartbeat, and data lines."""
    tkt, _, _ = await seed_isolated_swarm_scenario()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # A. Verify catchup via since_cursor with bounded max_events
        cursor = encode_cursor(datetime.utcnow() - timedelta(minutes=30), "seed")
        res = await asyncio.wait_for(
            client.get(f"/api/v1/swarm/stream?since_cursor={cursor}&ticket_number={tkt}&max_events=2"),
            timeout=5.0
        )
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        assert "no-cache" in res.headers["cache-control"]
        body = res.text
        assert ": connected" in body
        assert "id:" in body
        assert "event: swarm_event" in body
        assert "data:" in body
        assert tkt in body

        # B. Verify catchup via standard Last-Event-ID header
        res_header = await asyncio.wait_for(
            client.get(
                f"/api/v1/swarm/stream?ticket_number={tkt}&max_events=2",
                headers={"Last-Event-ID": cursor}
            ),
            timeout=5.0
        )
        assert res_header.status_code == 200
        assert ": connected" in res_header.text
        assert "event: swarm_event" in res_header.text
        assert tkt in res_header.text

        # C. Verify periodic heartbeat and live event broadcasting
        async def fetch_live():
            return await client.get("/api/v1/swarm/stream?heartbeat_interval=0.02&max_events=1")

        stream_task = asyncio.create_task(fetch_live())

        # Wait until client subscribes
        for _ in range(50):
            if len(swarm_service._subscribers) > 0:
                break
            await asyncio.sleep(0.01)

        # Allow at least one heartbeat interval to elapse
        await asyncio.sleep(0.06)

        # Broadcast a live event
        live_ev = SwarmActivityEvent(
            event_id=f"meko_live_{uuid.uuid4().hex[:6]}",
            source="MEKO_TOOL",
            timestamp=datetime.now(timezone.utc),
            actor="agent:frontdesk",
            actor_type="AGENT",
            event_type="CONTEXT_SEARCH",
            tool_name="context_search",
            status="SUCCESS",
            summary="Live context search stream test",
        )
        swarm_service.broadcast_event(live_ev)

        res_live = await asyncio.wait_for(stream_task, timeout=5.0)
        assert res_live.status_code == 200
        assert ": heartbeat" in res_live.text
        assert live_ev.event_id in res_live.text
        assert "event: swarm_event" in res_live.text


@pytest.mark.asyncio
async def test_12_sse_disconnect_cleanup():
    """12. SSE client disconnect cleans up internal subscription queue."""
    initial_subs = len(swarm_service._subscribers)

    # 1. Direct subscription and unsubscription unit test
    q = swarm_service.subscribe()
    assert len(swarm_service._subscribers) == initial_subs + 1
    swarm_service.unsubscribe(q)
    assert len(swarm_service._subscribers) == initial_subs

    # 2. HTTP SSE endpoint automatic cleanup upon stream completion
    tkt, _, _ = await seed_isolated_swarm_scenario()
    cursor = encode_cursor(datetime.utcnow() - timedelta(minutes=30), "seed")
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await asyncio.wait_for(
            client.get(f"/api/v1/swarm/stream?since_cursor={cursor}&ticket_number={tkt}&max_events=1"),
            timeout=5.0
        )
        assert res.status_code == 200

    # Ensure subscriber queue was unregistered upon generator completion
    assert len(swarm_service._subscribers) == initial_subs

    # 3. Slow/dead subscriber handling in broadcast_event
    dead_q = asyncio.Queue(maxsize=1)
    dead_q.put_nowait("existing")
    swarm_service._subscribers.add(dead_q)
    assert len(swarm_service._subscribers) == initial_subs + 1

    ev = SwarmActivityEvent(
        event_id=f"test_dead_{uuid.uuid4().hex[:6]}",
        source="GRIEVANCE",
        timestamp=datetime.now(timezone.utc),
        actor_type="SYSTEM",
        actor="system:workflow",
        event_type="DISPATCH_COMPLETED",
        status="SUCCESS",
        summary="Testing queue handling",
    )
    # Broadcast should not raise exception when queue is full
    swarm_service.broadcast_event(ev)
    swarm_service.unsubscribe(dead_q)
    assert len(swarm_service._subscribers) == initial_subs


@pytest.mark.asyncio
async def test_13_privacy_and_redaction():
    """13. No raw payloads, student IDs, staff tokens, or room numbers exposed."""
    tkt, _, _ = await seed_isolated_swarm_scenario()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get(f"/api/v1/swarm/events?ticket_number={tkt}")
        assert res.status_code == 200
        raw_text = res.text

        # Private student ID must NOT appear anywhere in output
        assert "student_anon_secret_id_44" not in raw_text
        # Staff reviewer ID must NOT appear in public feed
        assert "staff_supervisor_sharma" not in raw_text
        # Room number 204 was sanitized
        assert "room 204" not in raw_text.lower()
        # Raw arguments or responses JSON not exposed as un-sanitized fields
        assert "arguments_json" not in raw_text
        assert "response_json" not in raw_text


@pytest.mark.asyncio
async def test_14_failed_meko_call_fidelity():
    """14. Failed Meko tool calls remain accurately tagged with ERROR and is_fallback=True."""
    tkt, _, _ = await seed_isolated_swarm_scenario()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get(f"/api/v1/swarm/events?ticket_number={tkt}")
        assert res.status_code == 200
        events = res.json()["events"]

        failed_events = [e for e in events if e["status"] == "ERROR"]
        assert len(failed_events) >= 1
        assert failed_events[0]["is_fallback"] is True
        assert "error" in failed_events[0]["summary"].lower()


@pytest.mark.asyncio
async def test_15_existing_auth_and_approval_intact():
    """15. Existing staff approval endpoints remain fully protected by RBAC and tokens."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Missing token returns 401
        unauth_res = await client.get("/api/v1/approvals/pending")
        assert unauth_res.status_code == 401

        # READ_ONLY role returns 403 on decision submission
        readonly_res = await client.post(
            "/api/v1/approvals/TKT-TEST-999/decision",
            headers=AUTH_READONLY,
            json={"decision": "APPROVED"}
        )
        assert readonly_res.status_code == 403
