from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.auth import get_optional_current_student, get_current_student, StudentIdentity
from backend.app.models.grievance import Grievance, GrievanceStatus
from backend.app.models.approval import HumanApproval
from backend.app.models.escalation import VCEscalation
from backend.app.schemas.grievance import (
    GrievanceCreate,
    GrievanceWorkflowResponse,
    StudentGrievanceTrackResponse,
)
from backend.app.services.orchestrator import grievance_orchestrator

router = APIRouter()

@router.post(
    "/grievances",
    response_model=GrievanceWorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit student grievance through multi-agent swarm",
    description="Intakes complaint, runs Front Desk triage in cp-frontdesk, runs Dispatch assessment in cp-dispatch, and stores status."
)
async def submit_grievance(
    grievance_in: GrievanceCreate,
    student: Optional[StudentIdentity] = Depends(get_optional_current_student),
    db: AsyncSession = Depends(get_db),
):
    try:
        response = await grievance_orchestrator.process_new_grievance(
            grievance_in=grievance_in,
            db=db,
            student=student,
        )
        return response
    except PermissionError as perm_err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(perm_err)
        )
    except ValueError as val_err:
        err_msg = str(val_err)
        if "authentication" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=err_msg
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal processing error: {exc}"
        )

@router.get(
    "/student/grievances",
    summary="List authenticated student's submitted grievances",
    description="Returns grievances submitted by the currently authenticated student."
)
async def list_my_grievances(
    student: StudentIdentity = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Secure student endpoint to fetch their own grievances."""
    stmt = (
        select(Grievance)
        .where(Grievance.verified_student_id == student.student_id)
        .order_by(Grievance.created_at.desc())
    )
    res = await db.execute(stmt)
    records = res.scalars().all()
    return [
        {
            "id": g.id,
            "ticket_number": g.ticket_number,
            "title": g.title,
            "category": g.category.value if hasattr(g.category, "value") else str(g.category),
            "status": g.status.value if hasattr(g.status, "value") else str(g.status),
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "followup_count": g.followup_count or 1,
            "is_escalated_to_vc": g.is_escalated_to_vc or False,
            "thread_id": g.thread_id,
        }
        for g in records
    ]


@router.get(
    "/grievances/{ticket_number}/track",
    response_model=StudentGrievanceTrackResponse,
    summary="Track grievance progress for students",
    description="Returns public, privacy-filtered status and progress updates for a submitted grievance ticket."
)
async def track_grievance(
    ticket_number: str,
    student: Optional[StudentIdentity] = Depends(get_optional_current_student),
    db: AsyncSession = Depends(get_db),
):
    """
    Secure student-facing grievance tracking endpoint.
    Exposes only appropriate operational status and progress.
    Never exposes internal reviewer tokens, staff credentials, private staff notes,
    internal agent reasoning, Meko API keys, or another student's personal details.
    """
    clean_ticket = (ticket_number or "").strip()
    if not clean_ticket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket number must not be empty."
        )

    # 1. Fetch grievance by unique ticket number
    grievance = await db.scalar(
        select(Grievance).where(Grievance.ticket_number == clean_ticket)
    )
    if not grievance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grievance with ticket identifier '{clean_ticket}' not found."
        )

    # Ownership enforcement: If an authenticated student attempts to track another student's ticket
    if student and grievance.verified_student_id and grievance.verified_student_id != student.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not authorized to track this grievance ticket because it belongs to another student."
        )

    # 2. Determine student-friendly status explanation and latest update
    status_val = grievance.status.value if hasattr(grievance.status, "value") else str(grievance.status)
    is_awaiting_approval = (status_val == GrievanceStatus.PENDING_APPROVAL.value)

    if status_val == GrievanceStatus.PENDING_APPROVAL.value:
        status_explanation = (
            "Your grievance has been evaluated by automated intake triage and is currently "
            "awaiting operational review by campus staff."
        )
        latest_update = "Pending review and dispatch authorization by campus network staff."

    elif status_val == GrievanceStatus.APPROVED.value:
        status_explanation = (
            "Your grievance recommendation has been reviewed and approved by campus staff. "
            "Field technician dispatch is authorized."
        )
        dept_str = grievance.recommended_department or "technical team"
        latest_update = f"Operational dispatch authorized for {dept_str}. Field inspection scheduled."

    elif status_val == GrievanceStatus.REJECTED.value:
        status_explanation = (
            "Your grievance request was reviewed by campus staff and could not be approved "
            "for physical equipment replacement in its current form."
        )
        approval_rec = await db.scalar(
            select(HumanApproval).where(HumanApproval.grievance_id == grievance.id)
        )
        if approval_rec and approval_rec.reason:
            latest_update = f"Reviewed by campus staff: {approval_rec.reason}"
        else:
            latest_update = "Request reviewed by campus staff. Alternative remote remediation is being applied."

    elif status_val in [GrievanceStatus.TRIAGED.value, GrievanceStatus.SUBMITTED.value]:
        status_explanation = "Your grievance has been received and registered in the campus support system."
        latest_update = "Intake triage completed. Routine diagnostic checks in progress."

    elif status_val == GrievanceStatus.ASSIGNED.value:
        status_explanation = "Your grievance has been assigned to a technical field team for investigation."
        latest_update = f"Assigned to {grievance.recommended_department or 'technical staff'}."

    elif status_val == GrievanceStatus.RESOLVED.value:
        status_explanation = "The reported issue has been addressed and marked resolved."
        latest_update = "Issue resolution complete."

    elif status_val == GrievanceStatus.CLOSED.value:
        status_explanation = "This grievance ticket is closed."
        latest_update = "Ticket closed."

    else:
        status_explanation = f"Grievance status: {status_val}."
        latest_update = "Ticket logged in system."

    # Look up VC escalation info if escalated
    vc_status = None
    if grievance.is_escalated_to_vc and grievance.thread_id:
        esc_rec = await db.scalar(
            select(VCEscalation).where(VCEscalation.thread_id == grievance.thread_id)
        )
        if esc_rec:
            vc_status = esc_rec.status
            latest_update = (
                f"Ticket automatically escalated to Vice-Chancellor review queue ({esc_rec.status})."
            )
            status_explanation = (
                "This complaint has been escalated to the Vice-Chancellor's office for high-level "
                "administrative review due to multiple unresolved reports on this issue."
            )

    # 3. Return sanitized student-facing model
    return StudentGrievanceTrackResponse(
        ticket_number=grievance.ticket_number,
        category=grievance.category.value if hasattr(grievance.category, "value") else str(grievance.category),
        title=grievance.title,
        status=status_val,
        submitted_at=grievance.created_at,
        assigned_department=grievance.recommended_department,
        latest_update=latest_update,
        is_awaiting_approval=is_awaiting_approval,
        status_explanation=status_explanation,
    )


