from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.app.core.config import settings
from backend.app.core.database import init_db, get_db
from backend.app.models.meko_event import MekoEvent
from backend.app.models.grievance import Grievance
from backend.app.models.approval import HumanApproval
from backend.app.api.v1.grievances import router as grievances_router
from backend.app.api.v1.approvals import router as approvals_router
from backend.app.api.v1.swarm import router as swarm_router
from backend.app.api.v1.vc import router as vc_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    await init_db()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    description="CampusPulse AI - Multi-Agent Campus Grievance Swarm API (Phase 1)"
)

from backend.app.api.v1.auth import router as auth_router

allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
if getattr(settings, "FRONTEND_URL", None):
    allowed_origins.append(settings.FRONTEND_URL.rstrip("/"))
if getattr(settings, "ALLOWED_ORIGINS", None):
    for origin in settings.ALLOWED_ORIGINS.split(","):
        if origin.strip():
            allowed_origins.append(origin.strip().rstrip("/"))

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(grievances_router, prefix="/api/v1")
app.include_router(grievances_router, prefix="/api")
app.include_router(approvals_router, prefix="/api/v1/approvals", tags=["approvals"])
app.include_router(approvals_router, prefix="/api/approvals", tags=["approvals"])
app.include_router(swarm_router, prefix="/api/v1/swarm", tags=["swarm"])
app.include_router(swarm_router, prefix="/api/swarm", tags=["swarm"])
app.include_router(vc_router, prefix="/api/v1/vc", tags=["vice-chancellor"])
app.include_router(vc_router, prefix="/api/vc", tags=["vice-chancellor"])


@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    """Health status and configuration verification."""
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "runtime_datapacks": {
            "frontdesk": settings.MEKO_DATAPACK_FRONTDESK,
            "dispatch": settings.MEKO_DATAPACK_DISPATCH,
        },
        "llm_provider": settings.LLM_PROVIDER,
    }

@app.get("/api/v1/meko-events/history")
async def get_meko_events(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Retrieve audit history of genuine Meko MCP tool calls (No synthetic events)."""
    stmt = select(MekoEvent).order_by(desc(MekoEvent.timestamp)).limit(limit)
    res = await db.execute(stmt)
    events = res.scalars().all()
    return [
        {
            "id": e.id,
            "grievance_id": e.grievance_id,
            "agent_role": e.agent_role,
            "datapack_id": e.datapack_id,
            "tool_name": e.tool_name,
            "event_type": e.event_type,
            "status": e.status,
            "arguments": e.arguments_json,
            "response": e.response_json,
            "latency_ms": e.latency_ms,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
    ]
