import json
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.auth import (
    StaffIdentity,
    get_current_staff,
    verify_approval_permission,
    AI_AGENT_IDENTIFIERS,
)
from backend.app.models.grievance import Grievance, GrievanceStatus
from backend.app.models.approval import HumanApproval
from backend.app.schemas.approval import (
    ApprovalDecisionCreate,
    PendingApprovalItem,
    ApprovalDecisionResponse,
)

logger = logging.getLogger("campuspulse.audit.approvals")

router = APIRouter()

@router.get("/pending", response_model=List[PendingApprovalItem])
async def list_pending_approvals(
    current_staff: StaffIdentity = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all grievances currently awaiting human staff review.
    Requires authenticated staff token via X-Staff-Token header.
    """
    query = (
        select(Grievance)
        .where(Grievance.status == GrievanceStatus.PENDING_APPROVAL)
        .order_by(Grievance.created_at.asc())
    )
    result = await db.execute(query)
    grievances = result.scalars().all()

    items: List[PendingApprovalItem] = []
    for g in grievances:
        items.append(
            PendingApprovalItem(
                grievance_id=g.id,
                ticket_number=g.ticket_number,
                category=g.category.value if hasattr(g.category, "value") else str(g.category),
                urgency=g.urgency,
                location_ref=g.location_ref,
                title=g.title,
                description=g.description,
                status=g.status.value if hasattr(g.status, "value") else str(g.status),
                recommended_department=g.recommended_department,
                recommended_sla_hours=g.recommended_sla_hours,
                ai_recommendation=g.ai_recommendation,
                escalation_reason=g.escalation_reason,
                suggested_budget=3500.0 if "poe" in (g.ai_recommendation or "").lower() else 0.0,
                budget_currency="INR",
                budget_status="ILLUSTRATIVE_ESTIMATE" if "poe" in (g.ai_recommendation or "").lower() else "NOT_APPLICABLE",
                is_spending_authorized=False,
                meko_context_summary=g.meko_context_summary,
                created_at=g.created_at,
            )
        )
    return items

@router.post("/{ticket_number}/decision", response_model=ApprovalDecisionResponse)
async def submit_approval_decision_by_ticket(
    ticket_number: str,
    decision_in: ApprovalDecisionCreate,
    current_staff: StaffIdentity = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve or reject a grievance recommendation by ticket number.
    Requires valid X-Staff-Token. Reviewer identity and role are strictly
    resolved on the server from the token to prevent impersonation.
    """
    return await _process_approval_decision(ticket_number, decision_in, current_staff, db)

@router.post("/decision", response_model=ApprovalDecisionResponse)
async def submit_approval_decision_generic(
    decision_in: ApprovalDecisionCreate,
    ticket: Optional[str] = None,
    current_staff: StaffIdentity = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """Approve or reject a grievance recommendation using query param or payload ticket."""
    target_ticket = ticket or decision_in.ticket_number
    if not target_ticket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket number must be provided in URL or request body."
        )
    return await _process_approval_decision(target_ticket, decision_in, current_staff, db)

async def _process_approval_decision(
    ticket_number: str,
    decision_in: ApprovalDecisionCreate,
    current_staff: StaffIdentity,
    db: AsyncSession
) -> ApprovalDecisionResponse:
    """Core approval decision processor with token-based identity, RBAC, conflict prevention, and audit logging."""
    
    # 1. Enforce RBAC permissions for operational decision actions
    verify_approval_permission(current_staff)

    # 2. Block any attempt to inject an AI agent identity through payload body
    if decision_in.reviewer_id:
        clean_body_id = decision_in.reviewer_id.strip().lower()
        if any(agent_id in clean_body_id for agent_id in AI_AGENT_IDENTIFIERS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI agents are strictly forbidden from approving recommendations. A verified human staff member is required."
            )
    if decision_in.reviewer_role:
        clean_body_role = decision_in.reviewer_role.strip().lower()
        if any(agent_id in clean_body_role for agent_id in AI_AGENT_IDENTIFIERS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI agents are strictly forbidden from approving recommendations. A verified human staff member is required."
            )

    # 3. Derive effective identity strictly from authenticated token (ignore body overrides)
    effective_reviewer_id = current_staff.reviewer_id
    effective_reviewer_role = current_staff.reviewer_role

    # 4. Decision validation
    decision_type = decision_in.decision.strip().upper()
    if decision_type not in ["APPROVED", "REJECTED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid decision '{decision_in.decision}'. Allowed decisions: 'APPROVED', 'REJECTED'."
        )

    # 5. Mandatory reason for rejection
    if decision_type == "REJECTED":
        if not decision_in.reason or len(decision_in.reason.strip()) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A non-empty justification reason (at least 3 characters) is required when rejecting a recommendation."
            )

    # 6. Fetch target grievance
    clean_ticket = ticket_number.strip()
    grievance = await db.scalar(
        select(Grievance).where(
            (Grievance.ticket_number == clean_ticket) | 
            (Grievance.id == int(clean_ticket) if clean_ticket.isdigit() else False)
        )
    )
    if not grievance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grievance with ticket identifier '{ticket_number}' not found."
        )

    # 7. Check if grievance is in PENDING_APPROVAL status
    if grievance.status != GrievanceStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ticket '{grievance.ticket_number}' is not pending approval. "
                f"Current status is '{grievance.status.value}'. Conflicting decisions are disallowed."
            )
        )

    # 8. Prevent duplicate decisions
    existing_approval = await db.scalar(
        select(HumanApproval).where(HumanApproval.grievance_id == grievance.id)
    )
    if existing_approval:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket '{grievance.ticket_number}' already has a recorded decision ({existing_approval.decision})."
        )

    previous_status = grievance.status.value

    # 9. Snapshot original AI recommendation
    snapshot_data = {
        "recommended_department": grievance.recommended_department,
        "recommended_sla_hours": grievance.recommended_sla_hours,
        "ai_recommendation": grievance.ai_recommendation,
        "escalation_reason": grievance.escalation_reason,
        "meko_context_summary": grievance.meko_context_summary,
        "captured_at": grievance.updated_at.isoformat() if grievance.updated_at else None,
    }
    snapshot_json = json.dumps(snapshot_data)

    # 10. Transition status
    if decision_type == "APPROVED":
        new_status = GrievanceStatus.APPROVED.value
        grievance.status = GrievanceStatus.APPROVED
    else:
        new_status = GrievanceStatus.REJECTED.value
        grievance.status = GrievanceStatus.REJECTED

    # 11. Record HumanApproval record with authenticated staff identity
    approval_record = HumanApproval(
        grievance_id=grievance.id,
        ticket_number=grievance.ticket_number,
        reviewer_id=effective_reviewer_id,
        reviewer_role=effective_reviewer_role,
        decision=decision_type,
        reason=decision_in.reason.strip() if decision_in.reason else None,
        recommendation_snapshot=snapshot_json,
        assigned_technician=decision_in.assigned_technician.strip() if decision_in.assigned_technician else None,
        budget_authorized=0.0,  # Invariant: Human dispatch sign-off does NOT disburse financial funds
    )

    db.add(approval_record)
    await db.commit()
    await db.refresh(approval_record)
    await db.refresh(grievance)

    # Broadcast decision event to live swarm subscribers
    try:
        from backend.app.services.swarm_service import swarm_service
        norm_approval = swarm_service.normalize_approval_event(approval_record)
        swarm_service.broadcast_event(norm_approval)
    except Exception:
        pass

    # 12. Audit logging (tokens are never logged)
    logger.info(
        f"AUDIT_APPROVAL_DECISION: ticket={grievance.ticket_number} "
        f"reviewer_id={approval_record.reviewer_id} reviewer_role={approval_record.reviewer_role} "
        f"decision={approval_record.decision} previous_status={previous_status} new_status={new_status} "
        f"reason='{approval_record.reason}'"
    )

    return ApprovalDecisionResponse(
        approval_id=approval_record.id,
        grievance_id=grievance.id,
        ticket_number=grievance.ticket_number,
        reviewer_id=approval_record.reviewer_id,
        reviewer_role=approval_record.reviewer_role,
        decision=approval_record.decision,
        reason=approval_record.reason,
        previous_status=previous_status,
        new_status=new_status,
        assigned_technician=approval_record.assigned_technician,
        is_spending_authorized=False,
        financial_disclaimer=(
            "Human approval authorizes operational dispatch only. Real procurement, equipment purchasing, "
            "and financial disbursement are NOT authorized by this action."
        ),
        recommendation_snapshot=approval_record.recommendation_snapshot,
        decided_at=approval_record.created_at,
    )

