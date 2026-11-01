import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db, AsyncSessionLocal
from backend.app.schemas.swarm import (
    SwarmActivityFeedResponse,
    SwarmMetricsResponse,
    SwarmReplayResponse,
    SwarmActivityEvent,
)
from backend.app.services.swarm_service import (
    swarm_service,
    encode_cursor,
    decode_cursor,
)
from backend.app.core.auth import get_optional_session_user

logger = logging.getLogger("campuspulse.api.swarm")

async def verify_swarm_access(request: Request) -> None:
    session_user = await get_optional_session_user(request)
    if session_user and session_user.role == "STUDENT":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Students are not authorized to access the internal swarm dashboard."
        )

router = APIRouter(dependencies=[Depends(verify_swarm_access)])

# =============================================================================
# 1. Unified Activity Feed Endpoint
# =============================================================================

@router.get(
    "/feed",
    response_model=SwarmActivityFeedResponse,
    include_in_schema=False,
)
@router.get(
    "/events",
    response_model=SwarmActivityFeedResponse,
    summary="Unified Swarm Activity Feed",
    description="Retrieve chronologically ordered, normalized events across Meko tool calls, human approvals, and grievance milestones."
)
async def get_swarm_events(
    limit: int = Query(default=50, ge=1, le=200, description="Max number of events to return"),
    cursor: Optional[str] = Query(default=None, description="Composite pagination cursor (timestamp|event_id)"),
    ticket_number: Optional[str] = Query(default=None, description="Filter events for a specific ticket identifier"),
    agent_role: Optional[str] = Query(default=None, description="Filter events by agent role (frontdesk, dispatch, etc.)"),
    source: Optional[str] = Query(default=None, description="Filter by event source (MEKO_TOOL, HUMAN_APPROVAL, GRIEVANCE)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Public, privacy-safe, unified event feed.
    Zero raw API arguments, zero private student PII, and zero staff authentication tokens.
    """
    try:
        response = await swarm_service.get_activity_feed(
            db=db,
            limit=limit,
            cursor=cursor,
            ticket_number=ticket_number,
            agent_role=agent_role,
            source=source,
        )
        return response
    except Exception as exc:
        logger.error(f"Error querying swarm activity feed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to retrieve swarm activity feed: {exc}"
        )


# =============================================================================
# 2. Live Server-Sent Events (SSE) Stream
# =============================================================================

@router.get(
    "/stream",
    summary="Live Swarm Event Stream (SSE)",
    description="Real-time Server-Sent Events stream delivering newly recorded swarm activity. Supports reconnect recovery and heartbeat keep-alive."
)
async def stream_swarm_events(
    request: Request,
    since_cursor: Optional[str] = Query(default=None, description="Cursor for reconnect recovery"),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID", description="Standard SSE Last-Event-ID header"),
    ticket_number: Optional[str] = Query(default=None, description="Optional ticket filter for stream"),
    max_events: Optional[int] = Query(default=None, ge=1, description="Optional max events limit before closing stream (useful for bounded consumers and testing)"),
    heartbeat_interval: float = Query(default=15.0, gt=0, le=60.0, description="Heartbeat interval in seconds"),
):
    """
    Server-Sent Events endpoint using text/event-stream.
    - Sends catch-up events from the database if since_cursor / Last-Event-ID is provided.
    - Broadcasts live events from in-memory subscriber queue.
    - Sends periodic heartbeats (: heartbeat\\n\\n) based on heartbeat_interval.
    - Cleans up subscriptions cleanly upon client disconnect.
    - Bounded streaming support via max_events for tests or batch listeners.
    """
    recovery_cursor = last_event_id or since_cursor
    clean_ticket = ticket_number.strip().upper() if ticket_number else None

    # Pre-fetch catchup events before entering stream generator to close DB session cleanly
    catchup_events = []
    if recovery_cursor:
        async with AsyncSessionLocal() as catchup_db:
            try:
                catchup = await swarm_service.get_activity_feed(
                    db=catchup_db,
                    limit=100,
                    cursor=recovery_cursor,
                    ticket_number=clean_ticket,
                )
                catchup_events = catchup.events
            except Exception as err:
                logger.warning(f"Error during SSE catchup: {err}")

    async def event_generator() -> AsyncGenerator[str, None]:
        q = swarm_service.subscribe()
        seen_event_ids = set()
        yielded_count = 0

        try:
            yield ": connected\n\n"

            # 1. Recovery Catch-up: send missed historical events
            for ev in catchup_events:
                seen_event_ids.add(ev.event_id)
                cur = encode_cursor(ev.timestamp, ev.event_id)
                data_json = ev.model_dump_json()
                yield f"id: {cur}\nevent: swarm_event\ndata: {data_json}\n\n"
                yielded_count += 1
                if max_events is not None and yielded_count >= max_events:
                    return

            # 2. Live Stream Loop
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait up to heartbeat_interval seconds for a new event
                    event: SwarmActivityEvent = await asyncio.wait_for(q.get(), timeout=heartbeat_interval)

                    # Deduplicate if already delivered during catchup
                    if event.event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event.event_id)

                    # Apply optional ticket filter
                    if clean_ticket and event.ticket_number != clean_ticket:
                        continue

                    # Deliver event
                    cur = encode_cursor(event.timestamp, event.event_id)
                    data_json = event.model_dump_json()
                    yield f"id: {cur}\nevent: swarm_event\ndata: {data_json}\n\n"
                    yielded_count += 1
                    if max_events is not None and yielded_count >= max_events:
                        return

                except asyncio.TimeoutError:
                    # Send keep-alive heartbeat comment
                    now_iso = datetime.now(timezone.utc).isoformat()
                    yield f": heartbeat {now_iso}\n\n"

                except asyncio.CancelledError:
                    break

        finally:
            swarm_service.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# =============================================================================
# 3. Telemetry & Metrics Endpoint
# =============================================================================

@router.get(
    "/metrics",
    response_model=SwarmMetricsResponse,
    summary="Swarm Performance & Telemetry Metrics",
    description="Calculates genuine operational metrics and telemetry from recorded database events."
)
async def get_swarm_metrics(db: AsyncSession = Depends(get_db)):
    """Return genuine Meko latency, call volume, success rates, and human oversight counters."""
    try:
        return await swarm_service.get_metrics(db)
    except Exception as exc:
        logger.error(f"Error computing swarm metrics: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to calculate swarm metrics: {exc}"
        )


# =============================================================================
# 4. Historical Ticket Replay Endpoint
# =============================================================================

@router.get(
    "/replay",
    response_model=SwarmReplayResponse,
    summary="Ticket Lifecycle Replay Trace",
    description="Returns the recorded chronological event sequence for replaying a ticket's end-to-end swarm lifecycle."
)
async def get_ticket_replay(
    ticket_number: str = Query(..., min_length=3, description="Ticket identifier to replay (e.g. TKT-XXXXXXXX)"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full chronological trace for a ticket across all stages."""
    clean_ticket = ticket_number.strip().upper()
    replay = await swarm_service.get_ticket_replay(db, clean_ticket)
    if not replay:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No swarm activity or grievance found for ticket '{clean_ticket}'."
        )
    return replay
