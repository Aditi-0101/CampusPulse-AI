from datetime import datetime
from enum import Enum
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, UniqueConstraint
from backend.app.core.database import Base

class VCEscalationStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    FORWARDED_FOR_INVESTIGATION = "FORWARDED_FOR_INVESTIGATION"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"

class VCEscalationDecision(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    FORWARDED_FOR_INVESTIGATION = "FORWARDED_FOR_INVESTIGATION"
    RESOLVED = "RESOLVED"
    REJECTED_WITH_REASON = "REJECTED_WITH_REASON"

class VCEscalation(Base):
    """
    Vice-Chancellor Escalation Model:
    Automatically generated when the same verified student reports the same
    unresolved issue thread for the 3rd time without resolution by operational staff.
    Preserves human decision-making: AI agents cannot review or decide VC escalations.
    """
    __tablename__ = "vc_escalations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    escalation_id = Column(
        String(32),
        unique=True,
        index=True,
        default=lambda: f"ESC-{uuid.uuid4().hex[:8].upper()}"
    )
    
    # Thread reference - strictly unique constraint ensures no duplicate escalations per issue thread
    thread_id = Column(String(64), unique=True, index=True, nullable=False)
    verified_student_id = Column(String(64), index=True, nullable=False)
    
    category = Column(String(64), default="HOSTEL_WIFI", nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    location_ref = Column(String(64), nullable=False)
    
    # Metric counts & ticket correlation
    complaint_count = Column(Integer, default=3, nullable=False)
    related_tickets = Column(Text, nullable=False)  # JSON-encoded array: ["TKT-1", "TKT-2", "TKT-3"]
    trigger_ticket_number = Column(String(32), index=True, nullable=False)
    responsible_department = Column(String(128), default="Hostel Infrastructure & Network Operations", nullable=False)
    
    # Workflow status & review queue
    status = Column(String(32), default=VCEscalationStatus.PENDING_REVIEW.value, nullable=False)
    vc_queue = Column(String(32), default="VICE_CHANCELLOR", nullable=False)
    
    # Historical audit trail of prior operational decisions
    previous_authority_decisions = Column(Text, nullable=True)  # JSON array of previous human approvals/rejections
    
    # Vice-Chancellor human decision record (Zero AI decision-making)
    vc_decision = Column(String(64), nullable=True)
    vc_reviewer_id = Column(String(64), nullable=True)
    vc_remarks = Column(Text, nullable=True)
    
    escalated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("thread_id", name="uq_thread_vc_escalation"),
    )
