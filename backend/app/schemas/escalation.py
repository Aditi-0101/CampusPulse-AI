from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class VCEscalationSummaryResponse(BaseModel):
    """Safe, summarized representation of a Vice-Chancellor escalation."""
    escalation_id: str = Field(..., description="Unique escalation identifier (e.g. ESC-XXXXXXXX)")
    thread_id: str = Field(..., description="Underlying issue thread identifier (e.g. THR-XXXXXXXX)")
    complaint_count: int = Field(..., description="Total eligible unresolved complaints in this thread (3+)")
    category: str
    title: str
    location_ref: str
    responsible_department: str
    status: str = Field(..., description="Current escalation review status")
    trigger_ticket_number: str = Field(..., description="Ticket that triggered the 3rd complaint escalation threshold")
    related_tickets: List[str] = Field(default_factory=list, description="All ticket identifiers in this thread")
    escalated_at: datetime
    vc_decision: Optional[str] = None
    decided_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class VCEscalationDetailResponse(VCEscalationSummaryResponse):
    """Detailed representation of a Vice-Chancellor escalation with full audit trail."""
    description: str
    previous_authority_decisions: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Recorded human staff approval/rejection actions on prior tickets"
    )
    vc_reviewer_id: Optional[str] = None
    vc_remarks: Optional[str] = None
    linked_grievances: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Audit trace of individual grievance tickets in the thread"
    )

class VCDecisionPayload(BaseModel):
    """Payload for submitting a binding Vice-Chancellor escalation review decision."""
    decision: str = Field(
        ...,
        description="Decision type: ACKNOWLEDGED, ACTION_REQUIRED, FORWARDED_FOR_INVESTIGATION, RESOLVED, or REJECTED_WITH_REASON"
    )
    remarks: Optional[str] = Field(
        default=None,
        description="Reviewer justification or directive. Mandatory if decision is REJECTED_WITH_REASON."
    )

class VCDecisionResponse(BaseModel):
    """Response returned upon recording a Vice-Chancellor review decision."""
    escalation_id: str
    status: str
    vc_decision: str
    vc_reviewer_id: str
    vc_remarks: Optional[str] = None
    decided_at: datetime
    message: str
