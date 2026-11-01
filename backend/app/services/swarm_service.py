import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple, Set, AsyncGenerator
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.meko_event import MekoEvent
from backend.app.models.approval import HumanApproval
from backend.app.models.grievance import Grievance, GrievanceStatus
from backend.app.models.escalation import VCEscalation
from backend.app.schemas.swarm import (

    SwarmActivityEvent,
    SwarmActivityFeedResponse,
    SwarmMetricsResponse,
    SwarmRecentMetrics,
    SwarmReplayResponse,
)

logger = logging.getLogger("campuspulse.services.swarm")

def sanitize_display_text(text: Optional[str]) -> str:
    """Scrub room numbers, student IDs, or sensitive strings from display summaries and details."""
    if not text:
        return ""
    # Scrub room numbers like "room 204", "rm 204", "r-204"
    scrubbed = re.sub(r'\b(?:room|rm|r)[\s\-_]*\d{3,4}\b', 'zone', text, flags=re.IGNORECASE)
    # Scrub standalone 3-4 digit numbers
    scrubbed = re.sub(r'\b(\d{3,4})\b', 'zone', scrubbed)
    # Scrub student IDs
    scrubbed = re.sub(r'\buser_anon_\w+\b', 'student_user', scrubbed, flags=re.IGNORECASE)
    scrubbed = re.sub(r'\bstudent_anon_\w+\b', 'student_user', scrubbed, flags=re.IGNORECASE)
    return scrubbed

def encode_cursor(dt: datetime, event_id: str) -> str:
    """Encode (timestamp, event_id) into a URL-safe base64 composite cursor."""
    iso = dt.isoformat()
    raw = f"{iso}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")

def decode_cursor(cursor_str: str) -> Optional[Tuple[datetime, str]]:
    """Decode a composite cursor into (datetime, event_id). Returns None on error."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
        parts = raw.split("|", 1)
        if len(parts) != 2:
            return None
        dt_str, event_id = parts
        # Python 3.11 fromisoformat parses ISO strings seamlessly
        dt = datetime.fromisoformat(dt_str)
        # Ensure naive UTC datetimes are preserved consistently
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt, event_id
    except Exception as exc:
        logger.debug(f"Failed to decode cursor '{cursor_str}': {exc}")
        return None


class SwarmService:
    """
    Central service for CampusPulse AI Swarm observability.
    Normalizes genuine Meko tool calls, human approvals, and grievance milestones.
    Provides composite cursor pagination, telemetry metrics, replay traces, and SSE broadcasting.
    """

    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()

    # =========================================================================
    # SSE Subscription Management
    # =========================================================================

    def subscribe(self) -> asyncio.Queue:
        """Register a new SSE client subscriber with a bounded event queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        logger.debug(f"New SSE client subscribed. Total active listeners: {len(self._subscribers)}")
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unregister an SSE subscriber upon disconnect."""
        self._subscribers.discard(q)
        logger.debug(f"SSE client disconnected. Remaining listeners: {len(self._subscribers)}")

    def broadcast_event(self, event: SwarmActivityEvent) -> None:
        """Broadcast a newly recorded event to all connected live SSE listeners."""
        dead_queues = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow subscriber: drop oldest event to keep queue bounded and responsive
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass
            except Exception:
                dead_queues.append(q)

        for dq in dead_queues:
            self._subscribers.discard(dq)

    # =========================================================================
    # Event Normalization Helpers
    # =========================================================================

    @staticmethod
    def _sanitize_meko_summary(me: MekoEvent, ticket_number: Optional[str]) -> str:
        """Formulate a clean, privacy-safe, display-ready summary for a Meko tool event."""
        role_label = "Front Desk Agent" if me.agent_role == "frontdesk" else "Dispatch Routing Agent"
        tkt_str = f" for ticket {ticket_number}" if ticket_number else ""

        if me.tool_name == "context_search":
            datapack_label = "cp-frontdesk" if "frontdesk" in me.datapack_id else "cp-dispatch"
            if me.status == "ERROR":
                return f"{role_label} context search in {datapack_label}{tkt_str} encountered an error."
            return f"{role_label} searched {datapack_label}{tkt_str} for diagnostic context."

        elif me.tool_name == "conversation_create":
            return f"{role_label} initialized intake conversation trace container{tkt_str}."

        elif me.tool_name == "conversation_add_message":
            return f"{role_label} recorded student triage interaction turn{tkt_str}."

        elif me.tool_name == "memory_add":
            return f"{role_label} stored episodic infrastructure fact."

        return f"{role_label} executed genuine Meko tool '{me.tool_name}'{tkt_str}."

    @staticmethod
    def normalize_meko_event(
        me: MekoEvent,
        ticket_number: Optional[str] = None
    ) -> SwarmActivityEvent:
        """Convert a raw database MekoEvent into a unified SwarmActivityEvent."""
        is_fallback = False
        if me.status == "ERROR":
            is_fallback = True
        elif me.response_json:
            try:
                parsed = json.loads(me.response_json)
                if isinstance(parsed, dict) and parsed.get("is_error"):
                    is_fallback = True
            except Exception:
                pass

        summary = SwarmService._sanitize_meko_summary(me, ticket_number)

        # Build safe details dictionary (Zero raw payloads, Zero PII)
        details: Dict[str, Any] = {
            "agent_role": me.agent_role,
            "tool_name": me.tool_name,
            "event_type": me.event_type,
        }
        if ticket_number:
            details["ticket_number"] = ticket_number

        return SwarmActivityEvent(
            event_id=f"meko_{me.id}",
            source="MEKO_TOOL",
            timestamp=me.timestamp,
            actor_type="AGENT",
            actor=f"agent:{me.agent_role}",
            event_type=me.event_type,
            tool_name=me.tool_name,
            datapack_id=me.datapack_id,
            latency_ms=round(me.latency_ms, 2) if me.latency_ms is not None else None,
            ticket_number=ticket_number,
            status=me.status,
            summary=summary,
            is_fallback=is_fallback,
            details=details,
        )

    @staticmethod
    def normalize_approval_event(ha: HumanApproval) -> SwarmActivityEvent:
        """Convert a HumanApproval database record into a unified SwarmActivityEvent."""
        decision_upper = ha.decision.upper()
        event_type = f"DISPATCH_{decision_upper}"
        
        if decision_upper == "APPROVED":
            summary = f"Supervisor ({ha.reviewer_role}) authorized technician dispatch for ticket {ha.ticket_number}."
        else:
            summary = f"Supervisor ({ha.reviewer_role}) rejected recommendation for ticket {ha.ticket_number}."

        # Public details: display role, decision, technician; NEVER expose reviewer_id or private tokens
        details: Dict[str, Any] = {
            "decision": decision_upper,
            "reviewer_role": ha.reviewer_role,
        }
        if ha.assigned_technician:
            details["assigned_technician"] = ha.assigned_technician
        if ha.reason:
            details["justification"] = ha.reason

        return SwarmActivityEvent(
            event_id=f"approval_{ha.id}",
            source="HUMAN_APPROVAL",
            timestamp=ha.created_at,
            actor_type="HUMAN",
            actor=f"staff:{ha.reviewer_role}",
            event_type=event_type,
            tool_name=None,
            datapack_id=None,
            latency_ms=None,
            ticket_number=ha.ticket_number,
            status=decision_upper,
            summary=summary,
            is_fallback=None,
            details=details,
        )

    @staticmethod
    def normalize_grievance_milestones(g: Grievance) -> List[SwarmActivityEvent]:
        """Derive reliable lifecycle milestone events from a Grievance record."""
        events: List[SwarmActivityEvent] = []
        cat_str = g.category.value if hasattr(g.category, "value") else str(g.category)
        status_str = g.status.value if hasattr(g.status, "value") else str(g.status)

        # Milestone 1: Initial Submission
        events.append(
            SwarmActivityEvent(
                event_id=f"grievance_{g.id}_submitted",
                source="GRIEVANCE",
                timestamp=g.created_at,
                actor_type="SYSTEM",
                actor="system:intake",
                event_type="GRIEVANCE_SUBMITTED",
                tool_name=None,
                datapack_id=None,
                latency_ms=None,
                ticket_number=g.ticket_number,
                status="SUBMITTED",
                summary=f"Grievance ticket {g.ticket_number} registered in campus intake (Zone: {g.location_ref}).",
                is_fallback=None,
                details={
                    "category": cat_str,
                    "location_ref": g.location_ref,
                    "title": sanitize_display_text(g.title),
                },
            )
        )

        # Milestone 2: Triage Completion (if past SUBMITTED status)
        if status_str != "SUBMITTED":
            triage_time = g.created_at + timedelta(milliseconds=50)
            events.append(
                SwarmActivityEvent(
                    event_id=f"grievance_{g.id}_triaged",
                    source="GRIEVANCE",
                    timestamp=triage_time,
                    actor_type="AGENT",
                    actor="agent:frontdesk",
                    event_type="TRIAGE_COMPLETED",
                    tool_name=None,
                    datapack_id=None,
                    latency_ms=None,
                    ticket_number=g.ticket_number,
                    status="TRIAGED",
                    summary=f"Front Desk Agent completed triage for ticket {g.ticket_number} (Urgency: {g.urgency}).",
                    is_fallback=None,
                    details={
                        "urgency": g.urgency,
                        "is_duplicate": g.is_duplicate,
                        "duplicate_of_ticket": g.duplicate_of_ticket,
                    },
                )
            )

        # Milestone 3: Escalation for Human Staff Approval
        if g.requires_human_approval or status_str == "PENDING_APPROVAL":
            escalation_time = g.created_at + timedelta(milliseconds=100)
            events.append(
                SwarmActivityEvent(
                    event_id=f"grievance_{g.id}_escalated",
                    source="GRIEVANCE",
                    timestamp=escalation_time,
                    actor_type="AGENT",
                    actor="agent:dispatch",
                    event_type="ESCALATED_FOR_APPROVAL",
                    tool_name=None,
                    datapack_id=None,
                    latency_ms=None,
                    ticket_number=g.ticket_number,
                    status="PENDING_APPROVAL",
                    summary=f"Dispatch Agent routed ticket {g.ticket_number} to {g.recommended_department or 'NOC'} and flagged for staff approval.",
                    is_fallback=None,
                    details={
                        "recommended_department": g.recommended_department,
                        "recommended_sla_hours": g.recommended_sla_hours,
                        "escalation_reason": g.escalation_reason,
                    },
                )
            )

        return events

    @staticmethod
    def normalize_escalation_events(esc: VCEscalation) -> List[SwarmActivityEvent]:
        """Convert a VCEscalation record into workflow events (Never MEKO_TOOL, Zero PII)."""
        events: List[SwarmActivityEvent] = []
        # Event 1: VC Escalation Triggered
        events.append(
            SwarmActivityEvent(
                event_id=f"escalation_{esc.id}_triggered",
                source="GRIEVANCE",
                timestamp=esc.escalated_at,
                actor_type="SYSTEM",
                actor="system:escalation_engine",
                event_type="VC_ESCALATION_TRIGGERED",
                tool_name=None,
                datapack_id=None,
                latency_ms=None,
                ticket_number=esc.trigger_ticket_number,
                status=esc.status,
                summary=(
                    f"Automatic Vice-Chancellor escalation triggered for issue thread {esc.thread_id} "
                    f"({esc.complaint_count} unresolved complaints reported by verified student)."
                ),
                is_fallback=None,
                details={
                    "escalation_id": esc.escalation_id,
                    "thread_id": esc.thread_id,
                    "complaint_count": esc.complaint_count,
                },
            )
        )
        # Event 2: VC Review Decision (if decided)
        if esc.vc_decision and esc.decided_at:
            events.append(
                SwarmActivityEvent(
                    event_id=f"escalation_{esc.id}_decided",
                    source="HUMAN_APPROVAL",
                    timestamp=esc.decided_at,
                    actor_type="HUMAN",
                    actor="staff:VICE_CHANCELLOR",
                    event_type="VC_DECISION_RECORDED",
                    tool_name=None,
                    datapack_id=None,
                    latency_ms=None,
                    ticket_number=esc.trigger_ticket_number,
                    status=esc.status,
                    summary=f"Vice-Chancellor recorded decision: {esc.vc_decision} on escalation {esc.escalation_id}.",
                    is_fallback=None,
                    details={
                        "escalation_id": esc.escalation_id,
                        "thread_id": esc.thread_id,
                        "vc_decision": esc.vc_decision,
                        "vc_reviewer_role": "VICE_CHANCELLOR",
                    },
                )
            )
        return events

    # =========================================================================
    # Correlation Cache Builder
    # =========================================================================

    async def _build_correlation_maps(
        self,
        db: AsyncSession,
        grievance_ids: Optional[Set[int]] = None,
        ticket_number: Optional[str] = None,
    ) -> Tuple[Dict[int, str], Dict[str, str]]:
        """
        Build lookup maps from database:
        - grievance_id -> ticket_number
        - conversation_id -> ticket_number
        """
        id_to_ticket: Dict[int, str] = {}
        conv_to_ticket: Dict[str, str] = {}

        query = select(Grievance.id, Grievance.ticket_number, Grievance.conversation_id)
        if ticket_number:
            query = query.where(Grievance.ticket_number == ticket_number.strip().upper())
        elif grievance_ids:
            query = query.where(Grievance.id.in_(grievance_ids))

        res = await db.execute(query)
        for g_id, tkt, conv in res.all():
            if tkt:
                id_to_ticket[g_id] = tkt
                if conv:
                    conv_to_ticket[conv] = tkt

        return id_to_ticket, conv_to_ticket

    def _resolve_meko_ticket(
        self,
        me: MekoEvent,
        id_to_ticket: Dict[int, str],
        conv_to_ticket: Dict[str, str]
    ) -> Optional[str]:
        """
        Safely resolve ticket number for a MekoEvent without guessing:
        1. Direct grievance_id foreign key mapping
        2. Direct conversation_id mapping
        3. Explicit TKT-XXXXXXXX regex in sanitized title / arguments
        """
        # 1. Direct foreign key
        if me.grievance_id and me.grievance_id in id_to_ticket:
            return id_to_ticket[me.grievance_id]

        # 2. Check title or arguments for explicit ticket reference
        if me.arguments_json:
            match = re.search(r"TKT-[A-F0-9]{8}", me.arguments_json)
            if match:
                return match.group(0)

            # Check conversation_id in arguments
            try:
                args = json.loads(me.arguments_json)
                c_id = args.get("conversation_id")
                if c_id and c_id in conv_to_ticket:
                    return conv_to_ticket[c_id]
            except Exception:
                pass

        # 3. Check conversation_id in response (for conversation_create)
        if me.response_json:
            try:
                resp = json.loads(me.response_json)
                c_id = resp.get("id")
                if c_id and c_id in conv_to_ticket:
                    return conv_to_ticket[c_id]
            except Exception:
                pass

        return None

    # =========================================================================
    # Unified Activity Feed Query
    # =========================================================================

    async def get_activity_feed(
        self,
        db: AsyncSession,
        limit: int = 50,
        cursor: Optional[str] = None,
        ticket_number: Optional[str] = None,
        agent_role: Optional[str] = None,
        source: Optional[str] = None,
    ) -> SwarmActivityFeedResponse:
        """
        Query and return a chronological, normalized activity stream.
        Uses composite cursor pagination (timestamp, event_id) to guarantee zero duplicates or skips.
        """
        clean_limit = max(1, min(limit, 200))
        cursor_data = decode_cursor(cursor) if cursor else None
        cursor_dt = cursor_data[0] if cursor_data else None
        cursor_id = cursor_data[1] if cursor_data else None

        clean_ticket = ticket_number.strip().upper() if ticket_number else None
        clean_role = agent_role.strip().lower() if agent_role else None
        clean_source = source.strip().upper() if source else None

        # Build correlation lookups
        id_to_ticket, conv_to_ticket = await self._build_correlation_maps(db, ticket_number=clean_ticket)

        gathered_events: List[SwarmActivityEvent] = []

        # Pre-resolve target grievance for fast SQL filtering when ticket_number is specified
        target_g_id = None
        target_conv_id = None
        if clean_ticket:
            target_g = await db.scalar(
                select(Grievance).where(Grievance.ticket_number == clean_ticket)
            )
            if target_g:
                target_g_id = target_g.id
                target_conv_id = target_g.conversation_id

        # ---------------------------------------------------------------------
        # 1. Fetch Meko Tool Events (if source filter allows)
        # ---------------------------------------------------------------------
        if clean_source in [None, "MEKO_TOOL"]:
            meko_q = select(MekoEvent)
            if cursor_dt:
                meko_q = meko_q.where(MekoEvent.timestamp >= cursor_dt)
            if clean_role:
                meko_q = meko_q.where(MekoEvent.agent_role == clean_role)
            if clean_ticket:
                ticket_filters = [
                    MekoEvent.arguments_json.contains(clean_ticket),
                ]
                if target_g_id:
                    ticket_filters.append(MekoEvent.grievance_id == target_g_id)
                if target_conv_id:
                    ticket_filters.append(MekoEvent.arguments_json.contains(target_conv_id))
                    ticket_filters.append(MekoEvent.response_json.contains(target_conv_id))
                meko_q = meko_q.where(or_(*ticket_filters))

            # Order ascending chronologically
            meko_q = meko_q.order_by(MekoEvent.timestamp.asc(), MekoEvent.id.asc()).limit(clean_limit * 5)
            meko_res = await db.execute(meko_q)
            meko_rows = meko_res.scalars().all()

            # Ensure correlation map has all referenced grievance IDs
            missing_ids = {m.grievance_id for m in meko_rows if m.grievance_id and m.grievance_id not in id_to_ticket}
            if missing_ids:
                extra_id_map, extra_conv_map = await self._build_correlation_maps(db, grievance_ids=missing_ids)
                id_to_ticket.update(extra_id_map)
                conv_to_ticket.update(extra_conv_map)

            for m in meko_rows:
                resolved_ticket = self._resolve_meko_ticket(m, id_to_ticket, conv_to_ticket)
                # Apply ticket filter if specified
                if clean_ticket and resolved_ticket != clean_ticket:
                    continue

                gathered_events.append(self.normalize_meko_event(m, resolved_ticket))

        # ---------------------------------------------------------------------
        # 2. Fetch Human Approvals (if source filter allows and agent filter permits)
        # ---------------------------------------------------------------------
        if clean_source in [None, "HUMAN_APPROVAL"] and clean_role in [None, "human", "staff", "supervisor"]:
            ha_q = select(HumanApproval)
            if cursor_dt:
                ha_q = ha_q.where(HumanApproval.created_at >= cursor_dt)
            if clean_ticket:
                ha_q = ha_q.where(HumanApproval.ticket_number == clean_ticket)

            ha_q = ha_q.order_by(HumanApproval.created_at.asc(), HumanApproval.id.asc()).limit(clean_limit * 2)
            ha_res = await db.execute(ha_q)
            for ha in ha_res.scalars().all():
                gathered_events.append(self.normalize_approval_event(ha))

        # ---------------------------------------------------------------------
        # 3. Fetch Grievance Milestones (if source filter allows)
        # ---------------------------------------------------------------------
        if clean_source in [None, "GRIEVANCE"]:
            g_q = select(Grievance)
            if cursor_dt:
                # Include records created or updated after cursor timestamp
                g_q = g_q.where(or_(Grievance.created_at >= cursor_dt, Grievance.updated_at >= cursor_dt))
            if clean_ticket:
                g_q = g_q.where(Grievance.ticket_number == clean_ticket)

            g_q = g_q.order_by(Grievance.created_at.asc(), Grievance.id.asc()).limit(clean_limit * 2)
            g_res = await db.execute(g_q)
            for g in g_res.scalars().all():
                gathered_events.extend(self.normalize_grievance_milestones(g))

        # ---------------------------------------------------------------------
        # 3.5. Fetch VC Escalations (if source filter allows)
        # ---------------------------------------------------------------------
        if clean_source in [None, "GRIEVANCE", "HUMAN_APPROVAL"]:
            esc_q = select(VCEscalation)
            if cursor_dt:
                esc_q = esc_q.where(or_(VCEscalation.escalated_at >= cursor_dt, VCEscalation.decided_at >= cursor_dt))
            if clean_ticket:
                esc_q = esc_q.where(or_(
                    VCEscalation.trigger_ticket_number == clean_ticket,
                    VCEscalation.related_tickets.contains(clean_ticket)
                ))

            esc_res = await db.execute(esc_q)
            for esc in esc_res.scalars().all():
                for ev in self.normalize_escalation_events(esc):
                    if clean_source and ev.source != clean_source:
                        continue
                    gathered_events.append(ev)

        # ---------------------------------------------------------------------
        # 4. Strict Chronological Ordering & Cursor Filtering
        # ---------------------------------------------------------------------
        # Primary sort: timestamp ASC, Secondary tiebreaker: event_id ASC
        gathered_events.sort(key=lambda ev: (ev.timestamp, ev.event_id))

        # Filter strictly past cursor (eliminating duplicates with identical timestamps)
        if cursor_dt and cursor_id:
            filtered: List[SwarmActivityEvent] = []
            for ev in gathered_events:
                # Compare naive UTC datetimes
                ev_dt = ev.timestamp.replace(tzinfo=None) if ev.timestamp.tzinfo else ev.timestamp
                cur_dt = cursor_dt.replace(tzinfo=None) if cursor_dt.tzinfo else cursor_dt

                if ev_dt > cur_dt or (ev_dt == cur_dt and ev.event_id > cursor_id):
                    filtered.append(ev)
            gathered_events = filtered

        # Slice up to limit
        page_events = gathered_events[:clean_limit]
        has_more = len(gathered_events) > clean_limit

        next_cursor = None
        if has_more and page_events:
            last_ev = page_events[-1]
            last_dt = last_ev.timestamp.replace(tzinfo=None) if last_ev.timestamp.tzinfo else last_ev.timestamp
            next_cursor = encode_cursor(last_dt, last_ev.event_id)

        return SwarmActivityFeedResponse(
            events=page_events,
            next_cursor=next_cursor,
            has_more=has_more,
            total_returned=len(page_events),
        )

    # =========================================================================
    # Swarm Telemetry & Metrics
    # =========================================================================

    async def get_metrics(self, db: AsyncSession) -> SwarmMetricsResponse:
        """Calculate genuine telemetry counters and operational metrics from database."""
        # 1. Total Meko tool calls
        total_calls = await db.scalar(select(func.count(MekoEvent.id))) or 0

        # 2. Status counts
        success_calls = await db.scalar(
            select(func.count(MekoEvent.id)).where(MekoEvent.status == "SUCCESS")
        ) or 0
        error_calls = await db.scalar(
            select(func.count(MekoEvent.id)).where(MekoEvent.status == "ERROR")
        ) or 0

        # 3. Average latency
        avg_latency = await db.scalar(
            select(func.avg(MekoEvent.latency_ms)).where(MekoEvent.latency_ms > 0)
        ) or 0.0

        # 4. Context searches & memory recalls
        context_searches = await db.scalar(
            select(func.count(MekoEvent.id)).where(MekoEvent.tool_name == "context_search")
        ) or 0
        memory_recalls = await db.scalar(
            select(func.count(MekoEvent.id)).where(MekoEvent.event_type == "MEMORY_RECALLED")
        ) or 0

        # 5. Human approval and rejection counts
        human_approvals = await db.scalar(
            select(func.count(HumanApproval.id)).where(HumanApproval.decision == "APPROVED")
        ) or 0
        human_rejections = await db.scalar(
            select(func.count(HumanApproval.id)).where(HumanApproval.decision == "REJECTED")
        ) or 0

        # 6. Active agent roles
        agent_roles_res = await db.execute(select(MekoEvent.agent_role).distinct())
        agent_roles = sorted([r for r in agent_roles_res.scalars().all() if r])

        # 7. Recent metrics (Last 24 hours)
        cutoff_24h = datetime.utcnow() - timedelta(days=1)
        recent_total = await db.scalar(
            select(func.count(MekoEvent.id)).where(MekoEvent.timestamp >= cutoff_24h)
        ) or 0
        recent_success = await db.scalar(
            select(func.count(MekoEvent.id)).where(
                and_(MekoEvent.timestamp >= cutoff_24h, MekoEvent.status == "SUCCESS")
            )
        ) or 0
        recent_errors = await db.scalar(
            select(func.count(MekoEvent.id)).where(
                and_(MekoEvent.timestamp >= cutoff_24h, MekoEvent.status == "ERROR")
            )
        ) or 0
        recent_avg_latency = await db.scalar(
            select(func.avg(MekoEvent.latency_ms)).where(
                and_(MekoEvent.timestamp >= cutoff_24h, MekoEvent.latency_ms > 0)
            )
        ) or 0.0
        recent_recalls = await db.scalar(
            select(func.count(MekoEvent.id)).where(
                and_(MekoEvent.timestamp >= cutoff_24h, MekoEvent.event_type == "MEMORY_RECALLED")
            )
        ) or 0

        recent_metrics = SwarmRecentMetrics(
            window_description="Last 24 Hours",
            tool_calls=recent_total,
            successful_calls=recent_success,
            failed_calls=recent_errors,
            avg_latency_ms=round(recent_avg_latency, 2),
            memory_recalls=recent_recalls,
        )

        return SwarmMetricsResponse(
            total_meko_tool_calls=total_calls,
            successful_calls=success_calls,
            failed_calls=error_calls,
            avg_latency_ms=round(avg_latency, 2),
            context_searches_count=context_searches,
            memory_recalls_count=memory_recalls,
            human_approvals_count=human_approvals,
            human_rejections_count=human_rejections,
            active_agent_roles=agent_roles,
            time_window="ALL_TIME",
            recent_metrics=recent_metrics,
        )

    # =========================================================================
    # Historical Replay Trace
    # =========================================================================

    async def get_ticket_replay(
        self,
        db: AsyncSession,
        ticket_number: str
    ) -> Optional[SwarmReplayResponse]:
        """Generate a complete chronological trace for replaying a specific ticket's lifecycle."""
        clean_ticket = ticket_number.strip().upper()

        # 1. Fetch target grievance
        grievance = await db.scalar(
            select(Grievance).where(Grievance.ticket_number == clean_ticket)
        )
        if not grievance:
            # Check if ticket exists in human_approvals even if grievance record was cleared
            has_approval = await db.scalar(
                select(HumanApproval).where(HumanApproval.ticket_number == clean_ticket)
            )
            if not has_approval:
                return None

        # 2. Gather all events for this ticket
        feed = await self.get_activity_feed(
            db=db,
            limit=150,
            ticket_number=clean_ticket,
        )
        events = feed.events

        # 3. Analyze available vs unavailable stages
        available_stages: List[str] = []
        unavailable_stages: List[str] = []

        has_intake = any(e.event_type == "GRIEVANCE_SUBMITTED" for e in events)
        has_conv_init = any(e.event_type == "CONVERSATION_INIT" for e in events)
        has_triage = any(e.event_type == "TRIAGE_COMPLETED" for e in events)
        has_memory_search = any(e.event_type == "MEMORY_RECALLED" for e in events)
        has_escalation = any(e.event_type == "ESCALATED_FOR_APPROVAL" for e in events)
        has_approval = any(e.source == "HUMAN_APPROVAL" for e in events)

        if has_intake:
            available_stages.append("INTAKE_SUBMISSION")
        else:
            unavailable_stages.append("INTAKE_SUBMISSION")

        if has_conv_init:
            available_stages.append("MEKO_CONVERSATION_CONTAINER")
        else:
            unavailable_stages.append("MEKO_CONVERSATION_CONTAINER")

        if has_triage:
            available_stages.append("FRONTDESK_TRIAGE")
        else:
            unavailable_stages.append("FRONTDESK_TRIAGE")

        if has_memory_search:
            available_stages.append("MEKO_CONTEXT_SEARCH")
        else:
            unavailable_stages.append("MEKO_CONTEXT_SEARCH")

        if has_escalation:
            available_stages.append("DISPATCH_ESCALATION")
        else:
            unavailable_stages.append("DISPATCH_ESCALATION")

        if has_approval:
            available_stages.append("HUMAN_STAFF_OVERSIGHT")
        else:
            unavailable_stages.append("HUMAN_STAFF_OVERSIGHT")

        current_status = grievance.status.value if grievance and hasattr(grievance.status, "value") else (str(grievance.status) if grievance else "UNKNOWN")

        summary = (
            f"Chronological swarm replay for {clean_ticket} containing {len(events)} recorded event(s). "
            f"Current lifecycle status is '{current_status}'. "
            f"Completed stages: {', '.join(available_stages) if available_stages else 'None'}."
        )

        return SwarmReplayResponse(
            ticket_number=clean_ticket,
            current_status=current_status,
            events=events,
            available_stages=available_stages,
            unavailable_stages=unavailable_stages,
            summary=summary,
        )


# Global singleton service instance
swarm_service = SwarmService()
