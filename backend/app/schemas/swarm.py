from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

EventSource = Literal["MEKO_TOOL", "HUMAN_APPROVAL", "GRIEVANCE"]
ActorType = Literal["AGENT", "HUMAN", "SYSTEM"]

class SwarmActivityEvent(BaseModel):
    """
    Normalized, privacy-safe representation of an event in the CampusPulse AI Swarm.
    Integrates genuine Meko MCP tool calls, staff oversight decisions, and grievance milestones.
    """
    event_id: str = Field(..., description="Globally unique, stable event identifier (e.g. meko_123, approval_45)")
    source: EventSource = Field(..., description="Originating event source: MEKO_TOOL, HUMAN_APPROVAL, or GRIEVANCE")
    timestamp: datetime = Field(..., description="UTC timestamp of the recorded event")
    actor_type: ActorType = Field(..., description="Broad category of actor: AGENT, HUMAN, or SYSTEM")
    actor: str = Field(..., description="Safe identifier of the actor (e.g. agent:frontdesk, staff:NOC_SUPERVISOR)")
    event_type: str = Field(..., description="Specific operation or milestone (e.g. MEMORY_RECALLED, DISPATCH_APPROVED)")
    
    # Tool call specifics (Strictly null for non-tool events)
    tool_name: Optional[str] = Field(default=None, description="Actual Meko tool name if source == MEKO_TOOL")
    datapack_id: Optional[str] = Field(default=None, description="Target Meko datapack ID if source == MEKO_TOOL")
    latency_ms: Optional[float] = Field(default=None, description="Measured execution duration in milliseconds")
    
    # Context & Correlation
    ticket_number: Optional[str] = Field(default=None, description="Associated ticket number if reliably correlated")
    status: str = Field(..., description="Recorded execution or outcome status (SUCCESS, ERROR, APPROVED, REJECTED, etc.)")
    summary: str = Field(..., description="Concise, sanitized summary for UI display (Zero secrets, tokens, or PII)")
    is_fallback: Optional[bool] = Field(default=None, description="True if operation triggered deterministic baseline fallback")
    
    # Safe supplementary metadata (Redacted & filtered)
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Safe operational metadata attributes")

    model_config = {"from_attributes": True}


class SwarmActivityFeedResponse(BaseModel):
    """Paginated response containing normalized swarm activity events."""
    events: List[SwarmActivityEvent]
    next_cursor: Optional[str] = Field(default=None, description="Composite cursor for fetching subsequent events")
    has_more: bool = Field(default=False, description="Flag indicating if more records exist beyond the current page")
    total_returned: int = Field(default=0, description="Number of events returned in this page")


class SwarmRecentMetrics(BaseModel):
    """Metrics calculated over the recent activity window (last 24 hours / last 100 calls)."""
    window_description: str = Field(default="Last 24 Hours")
    tool_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    avg_latency_ms: float = 0.0
    memory_recalls: int = 0


class SwarmMetricsResponse(BaseModel):
    """Telemetry counters and operational metrics calculated from actual recorded database events."""
    total_meko_tool_calls: int = Field(..., description="Total genuine Meko MCP tool calls logged in database")
    successful_calls: int = Field(..., description="Tool calls completed with status SUCCESS")
    failed_calls: int = Field(..., description="Tool calls completed with status ERROR")
    avg_latency_ms: float = Field(..., description="Mean execution latency of recorded Meko tool calls")
    context_searches_count: int = Field(..., description="Number of context_search tool operations recorded")
    memory_recalls_count: int = Field(..., description="Total MEMORY_RECALLED events recorded across agents")
    human_approvals_count: int = Field(..., description="Total authorized human dispatch decisions")
    human_rejections_count: int = Field(..., description="Total human rejection / remediation decisions")
    active_agent_roles: List[str] = Field(default_factory=list, description="Unique agent and staff roles recorded")
    time_window: str = Field(default="ALL_TIME", description="Time window for all-time totals")
    recent_metrics: Optional[SwarmRecentMetrics] = Field(default=None, description="Recent window performance metrics")


class SwarmReplayResponse(BaseModel):
    """Structured chronological timeline for replaying a specific grievance ticket's lifecycle."""
    ticket_number: str
    current_status: Optional[str] = None
    events: List[SwarmActivityEvent] = Field(default_factory=list, description="Chronologically sorted lifecycle events")
    available_stages: List[str] = Field(default_factory=list, description="Stages with recorded historical evidence")
    unavailable_stages: List[str] = Field(default_factory=list, description="Stages missing or unreached in history")
    summary: str = Field(..., description="High-level narrative of the ticket lifecycle")
