import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.config import settings, validate_agent_datapack
from backend.app.core.database import init_db, AsyncSessionLocal
from backend.app.core.meko import meko_client
from backend.app.models.meko_event import MekoEvent
from sqlalchemy import select, desc

async def run_verification():
    print("--- 1. Testing Valid Meko Tool Call & Response Parsing ---")
    await init_db()

    # Create a conversation in cp-frontdesk
    conv_id = await meko_client.conversation_create(
        title="Verification Session",
        agent_role="frontdesk",
        datapack_id=settings.MEKO_DATAPACK_FRONTDESK,
    )
    print(f"Conversation ID created: {conv_id}")
    assert bool(conv_id), "Conversation ID must not be empty"

    # Call context_search
    search_res = await meko_client.context_search(
        query="Hostel 3 Wi-Fi connectivity",
        agent_role="frontdesk",
        conversation_id=conv_id,
        datapack_id=settings.MEKO_DATAPACK_FRONTDESK,
        limit=3,
    )
    print("Parsed context_search response keys:", list(search_res.keys()))
    assert "results" in search_res, "Response should have 'results' key"

    print("\n--- 2. Testing Error Handling (Invalid Tool Name) ---")
    err_res = await meko_client.call_tool(
        tool_name="non_existent_tool_123",
        arguments={"datapack_id": settings.MEKO_DATAPACK_FRONTDESK},
        agent_role="frontdesk",
    )
    print("Error response handled cleanly:", err_res)
    assert "error" in err_res or "code" in err_res or "message" in err_res, "Should capture error"

    print("\n--- 3. Testing Datapack Allowlist Enforcement (Frontdesk -> Dispatch Datapack) ---")
    frontdesk_blocked = False
    try:
        validate_agent_datapack("frontdesk", settings.MEKO_DATAPACK_DISPATCH)
    except PermissionError as e:
        frontdesk_blocked = True
        print(f"PASS: frontdesk blocked from cp-dispatch: {e}")
    assert frontdesk_blocked, "Frontdesk must not access cp-dispatch"

    print("\n--- 4. Testing Datapack Allowlist Enforcement (Dispatch -> Frontdesk Datapack) ---")
    dispatch_blocked = False
    try:
        validate_agent_datapack("dispatch", settings.MEKO_DATAPACK_FRONTDESK)
    except PermissionError as e:
        dispatch_blocked = True
        print(f"PASS: dispatch blocked from cp-frontdesk: {e}")
    assert dispatch_blocked, "Dispatch must not access cp-frontdesk"

    print("\n--- 5. Testing Database Event Persistence & Redaction in meko_events ---")
    async with AsyncSessionLocal() as session:
        stmt = select(MekoEvent).order_by(desc(MekoEvent.id)).limit(5)
        res = await session.execute(stmt)
        events = res.scalars().all()
        print(f"Found {len(events)} logged events in database.")
        for ev in events:
            print(f" - Event #{ev.id}: agent={ev.agent_role}, tool={ev.tool_name}, status={ev.status}, latency={ev.latency_ms}ms")
            # Verify no tokens leaked in arguments_json
            assert "mko_tkn_" not in ev.arguments_json, f"Token leaked in event {ev.id} arguments!"
            if ev.response_json:
                assert "mko_tkn_" not in ev.response_json, f"Token leaked in event {ev.id} response!"

    print("\n=== Verification Suite Completed Successfully ===")

if __name__ == "__main__":
    asyncio.run(run_verification())
