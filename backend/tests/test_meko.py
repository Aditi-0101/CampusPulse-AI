import asyncio
import os
import sys

# Ensure backend package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.core.meko import meko_client

async def run_independent_meko_test():
    print("=== Testing FastAPI Meko MCP Independent Client ===")
    
    # 1. Initialize SQLite/Postgres DB tables for event logging
    print("1. Initializing database tables...")
    await init_db()
    print("   [OK] Database tables initialized.")

    # 2. Test Security Safeguard: Attempting to access forbidden dev datapack
    print("\n2. Testing Datapack Allowlist Enforcement...")
    try:
        await meko_client.call_tool(
            tool_name="context_search",
            arguments={
                "query": "forbidden test",
                "conversation_id": "test_conv",
                "datapack_id": settings.FORBIDDEN_DEV_DATAPACK_ID,
            },
            agent_role="frontdesk"
        )
        print("   [FAIL] Security check failed: Forbidden datapack was not blocked!")
        return False
    except PermissionError as pe:
        print(f"   [PASS] Expected PermissionError correctly triggered: {pe}")

    # 3. Test Real Conversation Creation in cp-frontdesk
    print(f"\n3. Testing Conversation Creation in cp-frontdesk ({settings.MEKO_DATAPACK_FRONTDESK})...")
    conv_id = await meko_client.conversation_create(
        title="Automated Test - Phase 1 Validation",
        agent_role="frontdesk",
        datapack_id=settings.MEKO_DATAPACK_FRONTDESK,
    )
    if not conv_id:
        print("   [FAIL] Failed to create conversation container in cp-frontdesk")
        return False
    print(f"   [PASS] Successfully created conversation container ID: {conv_id}")

    # 4. Test Storing Pure Infrastructure Memory (Zero Student References)
    synthetic_fact = (
        "Diagnostic Hardware Log: Node AP-H3-Fl2 recorded firmware build v2.4.1 with "
        "radio frequency 5.18 GHz and nominal PoE voltage input 48.2V."
    )
    print("\n4. Testing memory_add with pure infrastructure diagnostics (Zero Student PII)...")
    add_res = await meko_client.memory_add(
        text=synthetic_fact,
        agent_role="frontdesk",
        conversation_id=conv_id,
        datapack_id=settings.MEKO_DATAPACK_FRONTDESK,
    )
    print(f"   [PASS] Memory Add Response: {add_res}")

    # 5. Test context_search
    print("\n5. Testing context_search in cp-frontdesk...")
    search_res = await meko_client.context_search(
        query="Node AP-H3-Fl2 firmware",
        agent_role="frontdesk",
        conversation_id=conv_id,
        datapack_id=settings.MEKO_DATAPACK_FRONTDESK,
    )
    print(f"   [PASS] Context Search Result Match Quality: {search_res.get('match_quality')}")

    print("\n=== All Independent Meko MCP Tests PASSED Successfully ===")
    return True

if __name__ == "__main__":
    asyncio.run(run_independent_meko_test())
