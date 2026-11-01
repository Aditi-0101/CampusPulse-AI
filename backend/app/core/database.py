from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from backend.app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def _sync_sqlite_schema(connection) -> None:
    """Safely apply non-destructive schema additions for SQLite without resetting database."""
    from sqlalchemy import text
    try:
        res = connection.execute(text("PRAGMA table_info(grievances);"))
        cols = {row[1] for row in res.fetchall()}
        if cols:
            if "verified_student_id" not in cols:
                connection.execute(text("ALTER TABLE grievances ADD COLUMN verified_student_id VARCHAR(64);"))
            if "thread_id" not in cols:
                connection.execute(text("ALTER TABLE grievances ADD COLUMN thread_id VARCHAR(64) DEFAULT '';"))
            if "followup_to_ticket" not in cols:
                connection.execute(text("ALTER TABLE grievances ADD COLUMN followup_to_ticket VARCHAR(32);"))
            if "followup_count" not in cols:
                connection.execute(text("ALTER TABLE grievances ADD COLUMN followup_count INTEGER DEFAULT 1;"))
            if "is_escalated_to_vc" not in cols:
                connection.execute(text("ALTER TABLE grievances ADD COLUMN is_escalated_to_vc BOOLEAN DEFAULT 0;"))

            connection.execute(text("UPDATE grievances SET thread_id = 'THR-' || SUBSTR(ticket_number, 5) WHERE thread_id IS NULL OR thread_id = '';"))
    except Exception:
        pass


async def init_db() -> None:
    """Create tables if they do not exist and apply non-destructive schema migrations."""
    # Ensure all models are registered on Base
    from backend.app.models.grievance import Grievance
    from backend.app.models.approval import HumanApproval
    from backend.app.models.meko_event import MekoEvent
    from backend.app.models.escalation import VCEscalation

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_sqlite_schema)
