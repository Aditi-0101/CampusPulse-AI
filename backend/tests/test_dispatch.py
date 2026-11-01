import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.core.meko import meko_client
from backend.app.schemas.grievance import GrievanceCreate, FrontDeskTriageResult
from backend.app.agents.dispatch import dispatch_agent

@pytest.mark.asyncio
async def test_dispatch_no_context_baseline():
    """Test deterministic baseline when no previous infrastructure context exists."""
    await init_db()

    # Triage result from Front Desk for unknown node
    triage = FrontDeskTriageResult(
        ticket_number="TKT-TEST0001",
        category="HOSTEL_WIFI",
        urgency="MEDIUM",
        is_duplicate=False,
        conversation_id="conv_test_unknown_001",
        meko_context_used=False,
        student_acknowledgment="Logged ticket TKT-TEST0001",
    )
    grievance_in = GrievanceCreate(
        title="Wi-Fi disconnects in room",
        description="Wi-Fi signal dropped unexpectedly this afternoon.",
        location_ref="node_loc_unknown_999",
    )

    recommendation = await dispatch_agent.assess_dispatch(triage, grievance_in)

    # Must be baseline, zero fabricated Meko memory
    assert recommendation.meko_context_retrieved is False
    assert len(recommendation.meko_supporting_facts) == 0
    assert recommendation.recommended_department == "Campus IT & Network Helpdesk"
    assert recommendation.recommended_sla_hours == 24
    assert recommendation.requires_human_approval is False
    assert "Deterministic Baseline" in recommendation.recommendation_reason
    print(f"\n[PASS] Baseline Dispatch: Dept={recommendation.recommended_department}, SLA={recommendation.recommended_sla_hours}h")

@pytest.mark.asyncio
async def test_dispatch_with_relevant_infrastructure_context():
    """Test Meko-augmented escalation when a verified hardware defect note exists in cp-dispatch."""
    # 1. Seed genuine infrastructure diagnostic fact into cp-dispatch
    conv_id = await meko_client.conversation_create(
        title="Admin Diagnostics - Hardware Notice",
        agent_role="dispatch",
        datapack_id=settings.MEKO_DATAPACK_DISPATCH,
    )
    
    diagnostic_note = (
        "Infrastructure Diagnostic Log: Node AP-H3-Fl2 has faulty PoE injector resetting under "
        "voltage drop below 210V. Physical hardware replacement required."
    )
    add_res = await meko_client.memory_add(
        text=diagnostic_note,
        agent_role="dispatch",
        conversation_id=conv_id,
        datapack_id=settings.MEKO_DATAPACK_DISPATCH,
    )
    memory_id = add_res.get("results", [{}])[0].get("id")

    # 2. Run Dispatch assessment for related grievance at infra_zone_h3_fl2
    triage = FrontDeskTriageResult(
        ticket_number="TKT-TEST0002",
        category="HOSTEL_WIFI",
        urgency="HIGH",
        is_duplicate=False,
        conversation_id=conv_id,
        meko_context_used=False,
        student_acknowledgment="Logged ticket TKT-TEST0002",
    )
    grievance_in = GrievanceCreate(
        title="Wi-Fi repeatedly resetting in Hostel 3 corridor AP-H3",
        description="Wi-Fi drops every evening after 7 PM in corridor near AP-H3.",
        location_ref="infra_zone_h3_fl2",
    )

    try:
        recommendation = await dispatch_agent.assess_dispatch(triage, grievance_in)

        # 3. Verify Meko-augmented escalation with illustrative estimate
        assert recommendation.meko_context_retrieved is True
        assert len(recommendation.meko_supporting_facts) > 0
        assert any("poe injector" in f.lower() or "voltage drop" in f.lower() for f in recommendation.meko_supporting_facts)
        assert recommendation.recommended_department == "Network Infrastructure Engineering (Specialized NOC)"
        assert recommendation.requires_human_approval is True
        assert recommendation.suggested_budget == 3500.0
        assert recommendation.budget_currency == "INR"
        assert recommendation.budget_status == "ILLUSTRATIVE_ESTIMATE"
        assert recommendation.is_spending_authorized is False
        assert recommendation.sla_status == "RECOMMENDED_TARGET"
        assert "illustrative estimate" in recommendation.escalation_reason.lower()
        print(f"[PASS] Meko-Augmented Escalation: Dept={recommendation.recommended_department}, Budget=₹{recommendation.suggested_budget} ({recommendation.budget_status})")
    finally:
        # 4. Clean up seeded memory from cp-dispatch
        if memory_id:
            await meko_client.call_tool(
                tool_name="memory_delete_by_id",
                arguments={
                    "memory_id": memory_id,
                    "agent_id": "product_agent:dispatch",
                    "datapack_id": settings.MEKO_DATAPACK_DISPATCH,
                    "conversation_id": conv_id,
                },
                agent_role="dispatch"
            )
            print("   [Cleaned up seeded test memory from cp-dispatch]")

@pytest.mark.asyncio
async def test_dispatch_cross_datapack_denial():
    """Verify that Dispatch Agent cannot access cp-frontdesk or campuspulse-build."""
    triage = FrontDeskTriageResult(
        ticket_number="TKT-TEST0003",
        category="HOSTEL_WIFI",
        urgency="MEDIUM",
        is_duplicate=False,
        conversation_id="conv_test_003",
        meko_context_used=False,
        student_acknowledgment="Logged ticket TKT-TEST0003",
    )
    grievance_in = GrievanceCreate(
        title="Test Wi-Fi",
        description="Testing unauthorized datapack access",
        location_ref="infra_zone_h3_fl2",
    )

    # Attempting to access cp-frontdesk
    with pytest.raises(PermissionError, match="Access Denied"):
        await dispatch_agent.assess_dispatch(
            triage,
            grievance_in,
            force_datapack_id=settings.MEKO_DATAPACK_FRONTDESK
        )

    # Attempting to access forbidden dev datapack campuspulse-build
    with pytest.raises(PermissionError, match="Security Violation"):
        await dispatch_agent.assess_dispatch(
            triage,
            grievance_in,
            force_datapack_id=settings.FORBIDDEN_DEV_DATAPACK_ID
        )

    print("[PASS] Cross-datapack access correctly denied for Dispatch Agent.")

@pytest.mark.asyncio
async def test_dispatch_safe_failure_handling():
    """Verify that a Meko failure/unreachable server safely falls back without fabricating facts."""
    triage = FrontDeskTriageResult(
        ticket_number="TKT-TEST0004",
        category="HOSTEL_WIFI",
        urgency="MEDIUM",
        is_duplicate=False,
        conversation_id="",  # Missing conversation_id causes Meko error
        meko_context_used=False,
        student_acknowledgment="Logged ticket TKT-TEST0004",
    )
    grievance_in = GrievanceCreate(
        title="Test Wi-Fi",
        description="Testing safe failure handling",
        location_ref="infra_zone_h3_fl2",
    )

    recommendation = await dispatch_agent.assess_dispatch(triage, grievance_in)

    # Must cleanly fallback and NOT claim Meko succeeded
    assert recommendation.meko_context_retrieved is False
    assert len(recommendation.meko_supporting_facts) == 0
    assert "Deterministic Baseline" in recommendation.recommendation_reason
    assert recommendation.budget_status == "NOT_APPLICABLE"
    assert recommendation.is_spending_authorized is False
    print("[PASS] Meko failure safely handled without fabricating memory.")

@pytest.mark.asyncio
async def test_dispatch_unconfigured_hardware_defect_not_invented():
    """Verify that an unconfigured hardware defect returns UNCONFIGURED status and 0 budget."""
    triage = FrontDeskTriageResult(
        ticket_number="TKT-TEST0005",
        category="HOSTEL_WIFI",
        urgency="HIGH",
        is_duplicate=False,
        conversation_id="conv_unconfigured",
        meko_context_used=False,
        student_acknowledgment="Logged ticket TKT-TEST0005",
    )
    grievance_in = GrievanceCreate(
        title="Fiber transceiver laser blown",
        description="Corridor switch distribution link is dark.",
        location_ref="infra_zone_h3_fl2",
    )

    # Evaluate directly with unconfigured hardware failure fact
    decision = dispatch_agent._evaluate_budget_and_sla(
        triage_urgency=triage.urgency,
        triage_category=triage.category,
        supporting_facts=["Diagnostic note: Core SFP+ transceiver laser defect on distribution switch."]
    )

    assert decision["budget_status"] == "UNCONFIGURED"
    assert decision["suggested_budget"] == 0.0
    assert decision["budget_currency"] == "INR"
    assert decision["is_spending_authorized"] is False
    assert decision["sla_status"] == "UNCONFIGURED"
    assert decision["requires_human_approval"] is True
    assert "no approved institutional pricing catalog exists" in decision["escalation_reason"].lower()
    print("[PASS] Unconfigured defect properly flagged: budget_status=UNCONFIGURED, budget=0.0")

@pytest.mark.asyncio
async def test_dispatch_never_authorizes_spending():
    """Verify that under NO circumstances can Dispatch Agent authorize spending."""
    triage = FrontDeskTriageResult(
        ticket_number="TKT-TEST0006",
        category="HOSTEL_WIFI",
        urgency="HIGH",
        is_duplicate=False,
        conversation_id="conv_safe",
        meko_context_used=False,
        student_acknowledgment="Logged ticket",
    )
    grievance_in = GrievanceCreate(
        title="Routine test",
        description="Routine description",
        location_ref="infra_zone_h3_fl2",
    )
    
    # 1. Baseline assessment
    rec = await dispatch_agent.assess_dispatch(triage, grievance_in)
    assert rec.is_spending_authorized is False

    # 2. Hardware replacement assessment
    decision = dispatch_agent._evaluate_budget_and_sla(
        triage_urgency="HIGH",
        triage_category="HOSTEL_WIFI",
        supporting_facts=["Hostel AP-H3 has faulty PoE injector hardware defect."]
    )
    assert decision["is_spending_authorized"] is False
    print("[PASS] Verified invariant: Dispatch Agent never independently authorizes spending.")

if __name__ == "__main__":
    asyncio.run(test_dispatch_no_context_baseline())
    asyncio.run(test_dispatch_with_relevant_infrastructure_context())
    asyncio.run(test_dispatch_cross_datapack_denial())
    asyncio.run(test_dispatch_safe_failure_handling())
    asyncio.run(test_dispatch_unconfigured_hardware_defect_not_invented())
    asyncio.run(test_dispatch_never_authorizes_spending())
    print("\n=== All Dispatch Agent Tests Passed Successfully ===")
