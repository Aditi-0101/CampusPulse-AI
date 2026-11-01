from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, ForeignKey
from backend.app.core.database import Base

class MekoEvent(Base):
    __tablename__ = "meko_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    grievance_id = Column(Integer, ForeignKey("grievances.id"), nullable=True, index=True)
    
    agent_role = Column(String(32), nullable=False, index=True)  # frontdesk, dispatch
    datapack_id = Column(String(64), nullable=False)
    tool_name = Column(String(64), nullable=False)               # context_search, memory_add, etc.
    event_type = Column(String(32), nullable=False)              # MEMORY_WRITTEN, MEMORY_RECALLED, etc.
    status = Column(String(16), default="PENDING")               # PENDING, SUCCESS, ERROR
    
    # Redacted payload snapshots (Never raw secrets)
    arguments_json = Column(Text, nullable=False)
    response_json = Column(Text, nullable=True)
    latency_ms = Column(Float, default=0.0)
    
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
