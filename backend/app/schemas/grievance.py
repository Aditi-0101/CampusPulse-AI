from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class GrievanceCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200, description="Short summary of the issue")
    description: str = Field(..., min_length=5, description="Detailed problem description")
    student_anon_id: str = Field(default="student_anon_user", description="Pseudonymous student ID (No PII)")
    location_ref: str = Field(default="infra_zone_h3_fl2", description="Non-identifying campus infrastructure zone reference")
    category: Optional[str] = Field(default="HOSTEL_WIFI", description="Preliminary category")
    # Stage H: Follow-up on existing unresolved complaint thread
    followup_ticket_number: Optional[str] = Field(default=None, description="Previous ticket number to follow up on (same issue thread)")

class FrontDeskTriageResult(BaseModel):
    ticket_number: str
    category: str
    urgency: str  # LOW, MEDIUM, HIGH, CRITICAL
    is_duplicate: bool = False
    duplicate_ticket_ref: Optional[str] = None
    conversation_id: str
    meko_context_used: bool = False
    meko_context_summary: Optional[str] = None
    student_acknowledgment: str

class DispatchRecommendation(BaseModel):
    ticket_number: str
    recommended_department: str
    recommended_sla_hours: int
    recommendation_reason: str
    meko_context_retrieved: bool = False
    meko_supporting_facts: List[str] = Field(default_factory=list)
    requires_human_approval: bool = False
    escalation_reason: Optional[str] = None
    suggested_budget: float = 0.0
    budget_currency: str = "INR"
    budget_status: str = "NOT_APPLICABLE"  # "ILLUSTRATIVE_ESTIMATE", "UNCONFIGURED", "NOT_APPLICABLE"
    is_spending_authorized: bool = False   # Invariant: AI agents NEVER independently authorize campus funds
    sla_status: str = "RECOMMENDED_TARGET" # "RECOMMENDED_TARGET", "UNCONFIGURED"
    pricing_disclaimer: str = (
        "Illustrative assumption for demo purposes. Not an official institutional quote. "
        "Formal financial expenditure requires authorized human staff approval."
    )

class GrievanceResponse(BaseModel):
    id: int
    ticket_number: str
    student_anon_id: str
    location_ref: str
    title: str
    description: str
    category: str
    urgency: str
    status: str
    conversation_id: Optional[str] = None
    ai_recommendation: Optional[str] = None
    recommended_department: Optional[str] = None
    recommended_sla_hours: int = 24
    meko_context_used: bool = False
    meko_context_summary: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of_ticket: Optional[str] = None
    requires_human_approval: bool = False
    escalation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class GrievanceWorkflowResponse(BaseModel):
    ticket_number: str
    status: str
    grievance_id: int
    triage: FrontDeskTriageResult
    dispatch: Optional[DispatchRecommendation] = None
    meko_context_used: bool = False
    meko_context_summary: Optional[str] = None
    requires_human_approval: bool = False
    escalation_reason: Optional[str] = None
    created_at: datetime
    # Stage H Threading & Escalation
    thread_id: Optional[str] = None
    followup_count: int = 1
    is_escalated_to_vc: bool = False
    escalation_id: Optional[str] = None

class StudentGrievanceTrackResponse(BaseModel):
    """
    Secure student-facing grievance tracking response.
    Exposes only appropriate operational status and progress.
    Omits internal tokens, credentials, DB primary keys, student IDs, and raw Meko memories.
    """
    ticket_number: str = Field(..., description="Unique grievance ticket identifier")
    category: str = Field(..., description="Complaint category")
    title: str = Field(..., description="Complaint title")
    status: str = Field(..., description="Current complaint workflow status")
    submitted_at: datetime = Field(..., description="Submission timestamp")
    assigned_department: Optional[str] = Field(None, description="Assigned resolving department, if available")
    latest_update: str = Field(..., description="Latest student-visible operational update")
    is_awaiting_approval: bool = Field(..., description="Whether the complaint is awaiting human staff approval")
    status_explanation: str = Field(..., description="Clear explanation of the current status")


