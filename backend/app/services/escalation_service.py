import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.grievance import Grievance, GrievanceStatus
from backend.app.models.approval import HumanApproval
from backend.app.models.escalation import VCEscalation, VCEscalationStatus, VCEscalationDecision
from backend.app.schemas.swarm import SwarmActivityEvent
from backend.app.services.swarm_service import swarm_service

logger = logging.getLogger("campuspulse.services.escalation")

class EscalationService:
    """
    Automatic Vice-Chancellor Escalation Engine.
    Enforces the 3rd-unresolved-complaint rule for the same verified student
    on the same issue thread.
    Preserves strict separation between automated counting and human governance.
    """

    async def evaluate_grievance_for_escalation(
        self,
        db: AsyncSession,
        grievance: Grievance,
    ) -> Optional[VCEscalation]:
        """
        Evaluate whether the given grievance triggers or belongs to a VC escalation.
        Rules:
        - Anonymous / unverified students NEVER trigger individual escalation.
        - Resolved or closed issues never trigger escalation.
        - Count strictly matching verified student + matching thread_id.
        - Exactly 3 unresolved complaints triggers atomic creation of VCEscalation.
        - 4th+ follow-ups attach to the existing escalation without creating duplicates.
        """
        # Rule: Only verified students can escalate
        if not grievance.verified_student_id or not grievance.verified_student_id.strip():
            logger.debug(f"Ticket {grievance.ticket_number} has no verified student ID; skipping VC escalation evaluation.")
            return None

        # Rule: Resolved or closed tickets cannot trigger escalation
        status_val = grievance.status.value if hasattr(grievance.status, "value") else str(grievance.status)
        if status_val in [GrievanceStatus.RESOLVED.value, GrievanceStatus.CLOSED.value]:
            logger.debug(f"Ticket {grievance.ticket_number} is resolved/closed; cannot trigger escalation.")
            return None

        thread_id = grievance.thread_id
        if not thread_id:
            logger.warning(f"Ticket {grievance.ticket_number} lacks thread_id; generating fallback.")
            thread_id = f"THR-{grievance.ticket_number.replace('TKT-', '')}"
            grievance.thread_id = thread_id

        # Query all eligible grievances in this thread from the same verified student
        stmt = (
            select(Grievance)
            .where(Grievance.thread_id == thread_id)
            .where(Grievance.verified_student_id == grievance.verified_student_id)
            .where(Grievance.status.notin_([GrievanceStatus.RESOLVED, GrievanceStatus.CLOSED]))
            .order_by(Grievance.created_at.asc(), Grievance.id.asc())
        )
        res = await db.execute(stmt)
        thread_grievances = list(res.scalars().all())

        # Ensure current grievance is in the list
        if not any(g.id == grievance.id for g in thread_grievances):
            thread_grievances.append(grievance)

        complaint_count = len(thread_grievances)
        grievance.followup_count = complaint_count

        # Check for existing escalation on this thread
        esc_stmt = select(VCEscalation).where(VCEscalation.thread_id == thread_id)
        existing_esc = await db.scalar(esc_stmt)

        related_ticket_numbers = [g.ticket_number for g in thread_grievances if g.ticket_number]

        if existing_esc:
            # Update existing escalation tickets and count without creating duplicate
            existing_esc.complaint_count = max(existing_esc.complaint_count, complaint_count)
            try:
                current_tickets = json.loads(existing_esc.related_tickets)
            except Exception:
                current_tickets = []
            
            for tkt in related_ticket_numbers:
                if tkt not in current_tickets:
                    current_tickets.append(tkt)
            existing_esc.related_tickets = json.dumps(current_tickets)
            grievance.is_escalated_to_vc = True
            await db.commit()
            await db.refresh(existing_esc)
            return existing_esc

        # Threshold check: Must be at least 3 complaints
        if complaint_count < 3:
            logger.info(
                f"Thread {thread_id} has {complaint_count}/3 complaints for student {grievance.verified_student_id}. "
                "Normal authority workflow preserved."
            )
            return None

        # Gather previous human authority decisions on earlier tickets
        decision_snapshots: List[Dict[str, Any]] = []
        for g in thread_grievances:
            if g.id != grievance.id:
                app_stmt = select(HumanApproval).where(HumanApproval.grievance_id == g.id)
                approvals = (await db.execute(app_stmt)).scalars().all()
                for app in approvals:
                    decision_snapshots.append({
                        "ticket_number": app.ticket_number,
                        "decision": app.decision,
                        "reason": app.reason,
                        "reviewer_role": app.reviewer_role,
                        "decided_at": app.created_at.isoformat() if app.created_at else None,
                    })

        # Create atomic VCEscalation record
        new_esc = VCEscalation(
            thread_id=thread_id,
            verified_student_id=grievance.verified_student_id,
            category=grievance.category.value if hasattr(grievance.category, "value") else str(grievance.category),
            title=grievance.title,
            description=grievance.description,
            location_ref=grievance.location_ref,
            complaint_count=complaint_count,
            related_tickets=json.dumps(related_ticket_numbers),
            trigger_ticket_number=grievance.ticket_number,
            responsible_department=grievance.recommended_department or "Hostel Infrastructure & Network Operations",
            status=VCEscalationStatus.PENDING_REVIEW.value,
            vc_queue="VICE_CHANCELLOR",
            previous_authority_decisions=json.dumps(decision_snapshots),
            escalated_at=datetime.utcnow(),
        )
        db.add(new_esc)
        grievance.is_escalated_to_vc = True

        # Commit atomically
        try:
            await db.commit()
            await db.refresh(new_esc)
        except Exception as commit_err:
            await db.rollback()
            existing = await db.scalar(select(VCEscalation).where(VCEscalation.thread_id == thread_id))
            if existing:
                grievance.is_escalated_to_vc = True
                await db.commit()
                return existing
            raise commit_err

        logger.info(
            f"VC Escalation triggered: {new_esc.escalation_id} for thread {thread_id} "
            f"(Triggered by {grievance.ticket_number}, count: {complaint_count})"
        )

        # Broadcast live swarm system event (strictly SYSTEM, not MEKO_TOOL)
        try:
            swarm_service.broadcast_event(
                SwarmActivityEvent(
                    event_id=f"escalation_{new_esc.id}_triggered",
                    source="GRIEVANCE",
                    timestamp=datetime.now(timezone.utc),
                    actor_type="SYSTEM",
                    actor="system:escalation_engine",
                    event_type="VC_ESCALATION_TRIGGERED",
                    ticket_number=grievance.ticket_number,
                    status=VCEscalationStatus.PENDING_REVIEW.value,
                    summary=(
                        f"Automatic Vice-Chancellor escalation triggered for issue thread {thread_id} "
                        f"(3 unresolved complaints reported by verified student)."
                    ),
                    details={
                        "escalation_id": new_esc.escalation_id,
                        "thread_id": thread_id,
                        "complaint_count": complaint_count,
                        "related_tickets": related_ticket_numbers,
                    }
                )
            )
        except Exception as broadcast_err:
            logger.warning(f"Failed to broadcast VC escalation event: {broadcast_err}")

        return new_esc

    async def record_vc_decision(
        self,
        db: AsyncSession,
        escalation: VCEscalation,
        decision: str,
        reviewer_id: str,
        remarks: Optional[str] = None,
    ) -> VCEscalation:
        """
        Record a binding Vice-Chancellor human review decision.
        Decisions: ACKNOWLEDGED, ACTION_REQUIRED, FORWARDED_FOR_INVESTIGATION, RESOLVED, REJECTED_WITH_REASON.
        Mandatory reason required for REJECTED_WITH_REASON.
        """
        clean_dec = decision.strip().upper()
        if clean_dec == "REJECTED_WITH_REASON" or clean_dec == "REJECTED":
            if not remarks or not remarks.strip():
                raise ValueError("A documented reason is mandatory when rejecting an escalation.")
            escalation.status = VCEscalationStatus.REJECTED.value
            escalation.vc_decision = VCEscalationDecision.REJECTED_WITH_REASON.value
        elif clean_dec == "RESOLVED":
            escalation.status = VCEscalationStatus.RESOLVED.value
            escalation.vc_decision = VCEscalationDecision.RESOLVED.value
        elif clean_dec == "ACTION_REQUIRED":
            escalation.status = VCEscalationStatus.ACTION_REQUIRED.value
            escalation.vc_decision = VCEscalationDecision.ACTION_REQUIRED.value
        elif clean_dec == "FORWARDED_FOR_INVESTIGATION" or clean_dec == "FORWARDED":
            escalation.status = VCEscalationStatus.FORWARDED_FOR_INVESTIGATION.value
            escalation.vc_decision = VCEscalationDecision.FORWARDED_FOR_INVESTIGATION.value
        elif clean_dec == "ACKNOWLEDGED":
            escalation.status = VCEscalationStatus.ACKNOWLEDGED.value
            escalation.vc_decision = VCEscalationDecision.ACKNOWLEDGED.value
        else:
            raise ValueError(f"Invalid Vice-Chancellor decision: '{decision}'")

        escalation.vc_reviewer_id = reviewer_id
        escalation.vc_remarks = remarks.strip() if remarks else None
        escalation.decided_at = datetime.utcnow()

        # If RESOLVED, also mark thread grievances as RESOLVED
        if escalation.status == VCEscalationStatus.RESOLVED.value:
            update_stmt = (
                select(Grievance)
                .where(Grievance.thread_id == escalation.thread_id)
            )
            g_list = (await db.execute(update_stmt)).scalars().all()
            for g in g_list:
                g.status = GrievanceStatus.RESOLVED

        await db.commit()
        await db.refresh(escalation)

        # Broadcast VC decision human event
        try:
            swarm_service.broadcast_event(
                SwarmActivityEvent(
                    event_id=f"escalation_{escalation.id}_decided",
                    source="HUMAN_APPROVAL",
                    timestamp=datetime.now(timezone.utc),
                    actor_type="HUMAN",
                    actor="staff:VICE_CHANCELLOR",
                    event_type="VC_DECISION_RECORDED",
                    ticket_number=escalation.trigger_ticket_number,
                    status=escalation.status,
                    summary=(
                        f"Vice-Chancellor recorded decision: {escalation.vc_decision} "
                        f"on escalation {escalation.escalation_id}."
                    ),
                    details={
                        "escalation_id": escalation.escalation_id,
                        "thread_id": escalation.thread_id,
                        "vc_decision": escalation.vc_decision,
                        "vc_reviewer_role": "VICE_CHANCELLOR",
                    }
                )
            )
        except Exception as b_err:
            logger.warning(f"Failed to broadcast VC decision event: {b_err}")

        return escalation

escalation_service = EscalationService()
