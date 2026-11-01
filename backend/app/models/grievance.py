from datetime import datetime
from enum import Enum
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, Enum as SQLEnum
from backend.app.core.database import Base

class GrievanceStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    TRIAGED = "TRIAGED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ASSIGNED = "ASSIGNED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class GrievanceCategory(str, Enum):
    HOSTEL_WIFI = "HOSTEL_WIFI"
    HOSTEL_ELECTRICITY = "HOSTEL_ELECTRICITY"
    OTHER = "OTHER"

class Grievance(Base):
    __tablename__ = "grievances"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticket_number = Column(String(32), unique=True, index=True, default=lambda: f"TKT-{uuid.uuid4().hex[:8].upper()}")
    
    # Synthetic student identifier & pseudonymous infrastructure zone (STRICT NO PII)
    student_anon_id = Column(String(64), index=True, nullable=False, default="student_anon_user")
    location_ref = Column(String(64), index=True, nullable=False, default="infra_zone_h3_fl2")
    
    # Stage H: Verified Student Identity & Issue Threading
    verified_student_id = Column(String(64), index=True, nullable=True)
    thread_id = Column(String(64), index=True, nullable=False, default=lambda: f"THR-{uuid.uuid4().hex[:8].upper()}")
    followup_to_ticket = Column(String(32), nullable=True)
    followup_count = Column(Integer, default=1, nullable=False)
    is_escalated_to_vc = Column(Boolean, default=False, nullable=False)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(SQLEnum(GrievanceCategory), default=GrievanceCategory.HOSTEL_WIFI, nullable=False)
    urgency = Column(String(16), default="MEDIUM")
    status = Column(SQLEnum(GrievanceStatus), default=GrievanceStatus.SUBMITTED, nullable=False)
    
    # Meko integration tracking
    conversation_id = Column(String(64), nullable=True)
    ai_recommendation = Column(Text, nullable=True)
    recommended_department = Column(String(128), nullable=True)
    recommended_sla_hours = Column(Integer, default=24)
    meko_context_used = Column(Boolean, default=False)
    meko_context_summary = Column(Text, nullable=True)
    
    # Duplicate tracking
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_ticket = Column(String(32), nullable=True)

    # Human-in-the-loop oversight
    requires_human_approval = Column(Boolean, default=False)
    escalation_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
