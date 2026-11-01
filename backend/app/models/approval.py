from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, ForeignKey, UniqueConstraint
from backend.app.core.database import Base

class HumanApproval(Base):
    """
    Human Approval Model:
    Stores authorized staff sign-offs on dispatch recommendations.
    Enforces human oversight: AI agents cannot self-approve or authorize funding.
    """
    __tablename__ = "human_approvals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    grievance_id = Column(Integer, ForeignKey("grievances.id"), nullable=False, index=True)
    ticket_number = Column(String(32), index=True, nullable=False)
    
    # Authorized staff reviewer credentials
    reviewer_id = Column(String(64), nullable=False)  # e.g. "staff_admin_sharma"
    reviewer_role = Column(String(64), nullable=False, default="CAMPUS_ADMIN")  # e.g. "NOC_SUPERVISOR", "CAMPUS_ADMIN"
    decision = Column(String(32), nullable=False)  # "APPROVED" or "REJECTED"
    reason = Column(Text, nullable=True)  # Mandatory for REJECTED, optional justification for APPROVED
    
    # Snapshot of the AI recommendation at decision time (preserves original AI output separately)
    recommendation_snapshot = Column(Text, nullable=True)
    
    # Operational fields (Disbursement & spending remain strictly False/unauthorized)
    budget_authorized = Column(Float, default=0.0)
    assigned_technician = Column(String(64), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("grievance_id", name="uq_grievance_approval"),
    )

    # Backwards-compatibility properties
    @property
    def staff_id(self) -> str:
        return self.reviewer_id

    @property
    def action(self) -> str:
        return self.decision

    @property
    def justification(self) -> str:
        return self.reason or ""
