import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.database import init_db
from backend.app.schemas.grievance import GrievanceCreate
from backend.app.agents.front_desk import front_desk_agent

@pytest.mark.asyncio
async def test_front_desk_standard_wifi_triage():
    """Test standard intake and triage for Wi-Fi outage."""
    await init_db()

    grievance = GrievanceCreate(
        title="Wi-Fi connectivity dropping in corridor",
        description="Wi-Fi signal frequently disconnects every 10 minutes on the 2nd floor.",
        student_anon_id="student_anon_user",
        location_ref="infra_zone_h3_fl2",
        category="HOSTEL_WIFI"
    )

    result = await front_desk_agent.triage_grievance(grievance)

    assert result.ticket_number.startswith("TKT-")
    assert result.category == "HOSTEL_WIFI"
    assert result.urgency == "MEDIUM"
    assert bool(result.conversation_id)
    assert "logged successfully under ticket" in result.student_acknowledgment
    print(f"\n[PASS] Standard Triage Ticket: {result.ticket_number}, Urgency: {result.urgency}")

@pytest.mark.asyncio
async def test_front_desk_high_urgency_triage():
    """Test urgency elevation when exam or total outage keywords are detected."""
    grievance = GrievanceCreate(
        title="Critical Wi-Fi failure during online exam",
        description="Students have an online test tomorrow morning and Wi-Fi has a total blackout.",
        student_anon_id="student_anon_user",
        location_ref="infra_zone_h3_fl2",
    )

    result = await front_desk_agent.triage_grievance(grievance)

    assert result.urgency == "HIGH"
    print(f"[PASS] Elevated Urgency Triage: {result.ticket_number}, Urgency: {result.urgency}")

@pytest.mark.asyncio
async def test_front_desk_validation_errors():
    """Test that missing or short required fields trigger validation errors."""
    from pydantic import ValidationError

    # Invalid short title
    with pytest.raises((ValidationError, ValueError)):
        GrievanceCreate(title="No", description="Valid description here", location_ref="infra_zone_h3_fl2")

    # Invalid short description
    with pytest.raises((ValidationError, ValueError)):
        GrievanceCreate(title="Valid Title", description="Bad", location_ref="infra_zone_h3_fl2")

    print("[PASS] Validation errors correctly caught for invalid inputs.")

if __name__ == "__main__":
    asyncio.run(test_front_desk_standard_wifi_triage())
    asyncio.run(test_front_desk_high_urgency_triage())
    asyncio.run(test_front_desk_validation_errors())
    print("\n=== All Front Desk Agent Tests Passed Successfully ===")
