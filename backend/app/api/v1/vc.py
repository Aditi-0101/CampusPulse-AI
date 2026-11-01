import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.auth import StaffIdentity, get_current_vc
from backend.app.models.escalation import VCEscalation, VCEscalationStatus
from backend.app.models.grievance import Grievance
from backend.app.schemas.escalation import (
    VCEscalationSummaryResponse,
    VCEscalationDetailResponse,
    VCDecisionPayload,
    VCDecisionResponse,
)
from backend.app.services.escalation_service import escalation_service

logger = logging.getLogger("campuspulse.api.vc")

router = APIRouter()

def _parse_json_list(val: Optional[str]) -> List[Any]:
    if not val:
        return []
    try:
        res = json.loads(val)
        return res if isinstance(res, list) else []
    except Exception:
        return []

@router.get(
    "/escalations",
    response_model=List[VCEscalationSummaryResponse],
    summary="List all Vice-Chancellor escalations",
    description="Protected endpoint for Vice-Chancellor portal to inspect escalated grievance threads."
)
async def list_escalations(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (e.g. PENDING_REVIEW, ACTION_REQUIRED, RESOLVED)"),
    current_vc: StaffIdentity = Depends(get_current_vc),
    db: AsyncSession = Depends(get_db),
):
    query = select(VCEscalation).order_by(VCEscalation.escalated_at.desc())
    if status_filter and status_filter.strip():
        query = query.where(VCEscalation.status == status_filter.strip().upper())

    result = await db.execute(query)
    escalations = result.scalars().all()

    items: List[VCEscalationSummaryResponse] = []
    for esc in escalations:
        items.append(
            VCEscalationSummaryResponse(
                escalation_id=esc.escalation_id,
                thread_id=esc.thread_id,
                complaint_count=esc.complaint_count,
                category=esc.category,
                title=esc.title,
                location_ref=esc.location_ref,
                responsible_department=esc.responsible_department,
                status=esc.status,
                trigger_ticket_number=esc.trigger_ticket_number,
                related_tickets=_parse_json_list(esc.related_tickets),
                escalated_at=esc.escalated_at,
                vc_decision=esc.vc_decision,
                decided_at=esc.decided_at,
            )
        )
    return items

@router.get(
    "/escalations/{escalation_id}",
    response_model=VCEscalationDetailResponse,
    summary="Get full audit trail for a Vice-Chancellor escalation",
    description="Returns detailed escalation records including linked complaints and prior authority actions."
)
async def get_escalation_detail(
    escalation_id: str,
    current_vc: StaffIdentity = Depends(get_current_vc),
    db: AsyncSession = Depends(get_db),
):
    clean_id = (escalation_id or "").strip()
    esc = await db.scalar(
        select(VCEscalation).where(VCEscalation.escalation_id == clean_id)
    )
    if not esc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Escalation record '{clean_id}' not found."
        )

    # Fetch individual grievances belonging to this thread
    g_query = (
        select(Grievance)
        .where(Grievance.thread_id == esc.thread_id)
        .order_by(Grievance.created_at.asc(), Grievance.id.asc())
    )
    g_res = await db.execute(g_query)
    thread_grievances = g_res.scalars().all()

    linked_grievances: List[Dict[str, Any]] = []
    for g in thread_grievances:
        linked_grievances.append({
            "ticket_number": g.ticket_number,
            "status": g.status.value if hasattr(g.status, "value") else str(g.status),
            "category": g.category.value if hasattr(g.category, "value") else str(g.category),
            "title": g.title,
            "description": g.description,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "recommended_department": g.recommended_department,
            "followup_count": g.followup_count,
            "location_ref": g.location_ref,
        })

    return VCEscalationDetailResponse(
        escalation_id=esc.escalation_id,
        thread_id=esc.thread_id,
        complaint_count=esc.complaint_count,
        category=esc.category,
        title=esc.title,
        description=esc.description,
        location_ref=esc.location_ref,
        responsible_department=esc.responsible_department,
        status=esc.status,
        trigger_ticket_number=esc.trigger_ticket_number,
        related_tickets=_parse_json_list(esc.related_tickets),
        escalated_at=esc.escalated_at,
        vc_decision=esc.vc_decision,
        decided_at=esc.decided_at,
        previous_authority_decisions=_parse_json_list(esc.previous_authority_decisions),
        vc_reviewer_id=esc.vc_reviewer_id,
        vc_remarks=esc.vc_remarks,
        linked_grievances=linked_grievances,
    )

@router.post(
    "/escalations/{escalation_id}/decision",
    response_model=VCDecisionResponse,
    summary="Record a binding Vice-Chancellor decision on an escalation",
    description="Submits official review decision (ACKNOWLEDGED, ACTION_REQUIRED, FORWARDED_FOR_INVESTIGATION, RESOLVED, REJECTED_WITH_REASON)."
)
async def submit_vc_decision(
    escalation_id: str,
    payload: VCDecisionPayload,
    current_vc: StaffIdentity = Depends(get_current_vc),
    db: AsyncSession = Depends(get_db),
):
    clean_id = (escalation_id or "").strip()
    esc = await db.scalar(
        select(VCEscalation).where(VCEscalation.escalation_id == clean_id)
    )
    if not esc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Escalation record '{clean_id}' not found."
        )

    try:
        updated_esc = await escalation_service.record_vc_decision(
            db=db,
            escalation=esc,
            decision=payload.decision,
            reviewer_id=current_vc.reviewer_id,
            remarks=payload.remarks,
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record Vice-Chancellor decision: {exc}"
        )

    return VCDecisionResponse(
        escalation_id=updated_esc.escalation_id,
        status=updated_esc.status,
        vc_decision=updated_esc.vc_decision,
        vc_reviewer_id=current_vc.reviewer_id,
        vc_remarks=updated_esc.vc_remarks,
        decided_at=updated_esc.decided_at,
        message=f"Vice-Chancellor review decision '{updated_esc.vc_decision}' successfully recorded.",
    )
