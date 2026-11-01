from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator

class ApprovalDecisionCreate(BaseModel):
    """
    Staff decision payload to approve or reject a pending grievance recommendation.
    Identity and role are resolved server-side from the X-Staff-Token header.
    Body-provided reviewer_id/reviewer_role are ignored for identity resolution to prevent impersonation.
    """
    decision: str = Field(..., description="Decision: APPROVED or REJECTED")
    reason: Optional[str] = Field(default=None, description="Justification for the decision. Mandatory when decision is REJECTED.")
    assigned_technician: Optional[str] = Field(default=None, description="Optional technician name/ID assigned to ticket")
    ticket_number: Optional[str] = Field(default=None, description="Optional ticket identifier if posting to /decision endpoint")
    
    # Deprecated fields: Ignored for identity resolution; strictly derived from X-Staff-Token
    reviewer_id: Optional[str] = Field(default=None, description="Deprecated/ignored: Identity is resolved from X-Staff-Token")
    reviewer_role: Optional[str] = Field(default=None, description="Deprecated/ignored: Role is resolved from X-Staff-Token")

    @field_validator("decision")
    @classmethod
    def validate_decision_enum(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in ["APPROVED", "REJECTED"]:
            raise ValueError("Decision must be either 'APPROVED' or 'REJECTED'.")
        return upper

class PendingApprovalItem(BaseModel):
    """Representation of a grievance awaiting human review."""
    grievance_id: int
    ticket_number: str
    category: str
    urgency: str
    location_ref: str
    title: str
    description: str
    status: str
    recommended_department: Optional[str] = None
    recommended_sla_hours: Optional[int] = None
    ai_recommendation: Optional[str] = None
    escalation_reason: Optional[str] = None
    suggested_budget: float = 0.0
    budget_currency: str = "INR"
    budget_status: str = "ILLUSTRATIVE_ESTIMATE"
    is_spending_authorized: bool = False
    meko_context_summary: Optional[str] = None
    created_at: datetime

class ApprovalDecisionResponse(BaseModel):
    """Response returned upon recording a human approval or rejection decision."""
    approval_id: int
    grievance_id: int
    ticket_number: str
    reviewer_id: str
    reviewer_role: str
    decision: str
    reason: Optional[str] = None
    previous_status: str
    new_status: str
    assigned_technician: Optional[str] = None
    is_spending_authorized: bool = False
    financial_disclaimer: str = (
        "Human approval authorizes operational dispatch only. Real procurement, equipment purchasing, "
        "and financial disbursement are NOT authorized by this action."
    )
    recommendation_snapshot: Optional[str] = None
    decided_at: datetime
