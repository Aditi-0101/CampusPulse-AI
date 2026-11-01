import logging
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.app.core.auth import StudentIdentity
from backend.app.models.grievance import Grievance, GrievanceStatus, GrievanceCategory
from backend.app.schemas.grievance import (
    GrievanceCreate,
    FrontDeskTriageResult,
    DispatchRecommendation,
    GrievanceWorkflowResponse,
)
from backend.app.agents.front_desk import front_desk_agent
from backend.app.agents.dispatch import dispatch_agent
from backend.app.services.escalation_service import escalation_service

logger = logging.getLogger("campuspulse.services.orchestrator")

class GrievanceOrchestrationService:
    """Orchestrates end-to-end multi-agent grievance intake, triage, dispatch, persistence, and VC escalation."""

    async def process_new_grievance(
        self,
        grievance_in: GrievanceCreate,
        db: AsyncSession,
        student: Optional[StudentIdentity] = None,
    ) -> GrievanceWorkflowResponse:
        """Execute Front Desk -> Dispatch workflow with strict DB persistence, follow-up threading, and VC escalation."""
        
        # 1. Pre-validation: ensure input meets schema requirements
        if not grievance_in.title or len(grievance_in.title.strip()) < 3:
            raise ValueError("Grievance title must be at least 3 characters long.")
        if not grievance_in.description or len(grievance_in.description.strip()) < 5:
            raise ValueError("Grievance description must be at least 5 characters long.")
        if not grievance_in.location_ref:
            raise ValueError("Location reference (node_loc_...) is required.")

        # 2. Stage H: Handle Follow-up vs New Issue Thread
        thread_id: Optional[str] = None
        followup_to_ticket: Optional[str] = None
        followup_count: int = 1

        if grievance_in.followup_ticket_number and grievance_in.followup_ticket_number.strip():
            clean_parent_ticket = grievance_in.followup_ticket_number.strip()
            if not student or not student.student_id:
                raise ValueError("Follow-up complaints require verified student authentication.")

            # Verify parent ticket
            parent_stmt = select(Grievance).where(Grievance.ticket_number == clean_parent_ticket)
            parent = await db.scalar(parent_stmt)
            if not parent:
                raise ValueError(f"Previous ticket '{clean_parent_ticket}' not found.")

            # Verify ownership: student can only follow up on their own complaints
            if not parent.verified_student_id or parent.verified_student_id != student.student_id:
                raise PermissionError("Access denied: You cannot follow up on a complaint submitted by another student.")

            # Verify unresolved: cannot follow up on resolved/closed issues
            parent_status = parent.status.value if hasattr(parent.status, "value") else str(parent.status)
            if parent_status in [GrievanceStatus.RESOLVED.value, GrievanceStatus.CLOSED.value]:
                raise ValueError(f"Cannot follow up on ticket '{parent.ticket_number}' because it is already {parent_status}.")

            thread_id = parent.thread_id or f"thread_{parent.ticket_number}"
            if not parent.thread_id:
                parent.thread_id = thread_id
                await db.commit()

            followup_to_ticket = parent.ticket_number
            # Count prior complaints in this thread
            count_stmt = select(func.count(Grievance.id)).where(Grievance.thread_id == thread_id)
            prior_count = (await db.scalar(count_stmt)) or 0
            followup_count = prior_count + 1
        else:
            # New complaint creates a provisional thread_id
            thread_id = f"thread_temp_{uuid.uuid4().hex[:8]}"
            followup_count = 1

        # 3. Persist initial SUBMITTED grievance in database
        initial_grievance = Grievance(
            student_anon_id=grievance_in.student_anon_id,
            verified_student_id=student.student_id if student else None,
            thread_id=thread_id,
            followup_to_ticket=followup_to_ticket,
            followup_count=followup_count,
            location_ref=grievance_in.location_ref,
            title=grievance_in.title,
            description=grievance_in.description,
            category=GrievanceCategory.HOSTEL_WIFI,
            status=GrievanceStatus.SUBMITTED,
        )
        db.add(initial_grievance)
        await db.commit()
        await db.refresh(initial_grievance)

        # 4. Stage 1: Front Desk Agent Triage
        triage_result: Optional[FrontDeskTriageResult] = None
        try:
            triage_result = await front_desk_agent.triage_grievance(
                grievance_in=grievance_in,
                grievance_id=initial_grievance.id,
            )
            # Synchronize ticket number and triage fields across DB
            initial_grievance.ticket_number = triage_result.ticket_number
            initial_grievance.category = GrievanceCategory(triage_result.category) if triage_result.category in GrievanceCategory.__members__ else GrievanceCategory.OTHER
            initial_grievance.urgency = triage_result.urgency
            initial_grievance.conversation_id = triage_result.conversation_id
            initial_grievance.is_duplicate = triage_result.is_duplicate
            initial_grievance.duplicate_of_ticket = triage_result.duplicate_ticket_ref
            initial_grievance.meko_context_used = triage_result.meko_context_used
            initial_grievance.meko_context_summary = triage_result.meko_context_summary
            initial_grievance.status = GrievanceStatus.TRIAGED

            # Canonicalize thread_id for initial ticket
            if initial_grievance.thread_id.startswith("thread_temp_"):
                initial_grievance.thread_id = f"thread_{initial_grievance.ticket_number}"

            await db.commit()
            await db.refresh(initial_grievance)
        except Exception as exc:
            await db.rollback()
            logger.error(f"Front Desk triage failed for grievance #{initial_grievance.id}: {exc}")
            try:
                g = await db.get(Grievance, initial_grievance.id)
                if g:
                    g.ai_recommendation = f"Front Desk intake error: {exc}"
                    await db.commit()
            except Exception:
                pass
            raise RuntimeError(f"Front Desk Agent failed: {exc}") from exc

        # 5. Stage 2: Dispatch Agent Routing Assessment
        dispatch_result: Optional[DispatchRecommendation] = None
        try:
            dispatch_result = await dispatch_agent.assess_dispatch(
                triage=triage_result,
                grievance_input=grievance_in,
                grievance_id=initial_grievance.id,
            )
            
            # Combine Meko context attribution from both agents
            combined_meko_used = triage_result.meko_context_used or dispatch_result.meko_context_retrieved
            summaries = []
            if triage_result.meko_context_used and triage_result.meko_context_summary:
                summaries.append(f"Front Desk: {triage_result.meko_context_summary}")
            if dispatch_result.meko_context_retrieved and dispatch_result.meko_supporting_facts:
                summaries.append(f"Dispatch: Found {len(dispatch_result.meko_supporting_facts)} infrastructure fact(s)")
            
            initial_grievance.recommended_department = dispatch_result.recommended_department
            initial_grievance.recommended_sla_hours = dispatch_result.recommended_sla_hours
            initial_grievance.ai_recommendation = dispatch_result.recommendation_reason
            initial_grievance.meko_context_used = combined_meko_used
            initial_grievance.meko_context_summary = " | ".join(summaries) if summaries else "No historical Meko context found."
            initial_grievance.requires_human_approval = dispatch_result.requires_human_approval
            initial_grievance.escalation_reason = dispatch_result.escalation_reason

            # Determine next status: if human approval required, transition to PENDING_APPROVAL
            if dispatch_result.requires_human_approval:
                initial_grievance.status = GrievanceStatus.PENDING_APPROVAL
            else:
                initial_grievance.status = GrievanceStatus.TRIAGED

            await db.commit()
            await db.refresh(initial_grievance)

        except Exception as exc:
            logger.error(f"Dispatch assessment failed for grievance #{initial_grievance.id}: {exc}")
            initial_grievance.ai_recommendation = f"Dispatch assessment failed: {exc}"
            await db.commit()
            await db.refresh(initial_grievance)

        # 6. Stage H: Evaluate Automatic Vice-Chancellor Escalation
        escalation_rec = None
        try:
            escalation_rec = await escalation_service.evaluate_grievance_for_escalation(
                db=db,
                grievance=initial_grievance,
            )
        except Exception as esc_err:
            logger.error(f"VC escalation evaluation error for grievance #{initial_grievance.id}: {esc_err}")

        return GrievanceWorkflowResponse(
            ticket_number=initial_grievance.ticket_number,
            status=initial_grievance.status.value,
            grievance_id=initial_grievance.id,
            triage=triage_result,
            dispatch=dispatch_result,
            meko_context_used=initial_grievance.meko_context_used,
            meko_context_summary=initial_grievance.meko_context_summary,
            requires_human_approval=initial_grievance.requires_human_approval,
            escalation_reason=initial_grievance.escalation_reason,
            created_at=initial_grievance.created_at,
            thread_id=initial_grievance.thread_id,
            followup_count=initial_grievance.followup_count,
            is_escalated_to_vc=initial_grievance.is_escalated_to_vc,
            escalation_id=escalation_rec.escalation_id if escalation_rec else None,
        )

grievance_orchestrator = GrievanceOrchestrationService()

