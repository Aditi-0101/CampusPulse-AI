import os
from typing import Dict, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "CampusPulse AI"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = Field(
        default="campuspulse_secret_session_key_2026_dev_secure",
        description="HMAC signing key for secure HttpOnly session cookies"
    )
    SESSION_COOKIE_NAME: str = "campuspulse_session"
    SESSION_MAX_AGE_SECONDS: int = 86400  # 24 hours
    
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    FRONTEND_URL: Optional[str] = None
    ALLOWED_ORIGINS: str = ""

    # Database: Async SQLAlchemy URL (SQLite for instant local dev or PostgreSQL)
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./campuspulse_dev.db",
        description="Async database connection string"
    )
    
    # Meko MCP Endpoint (Backend ONLY - Never sent to frontend)
    MEKO_SERVER_URL: str = Field(
        default="https://mcp.mekodata.ai/mcp",
        description="Remote Meko MCP server URL"
    )
    MEKO_API_KEY: str = Field(
        default="",
        description="Meko Authorization Bearer token"
    )

    # Runtime Datapacks (Strict Isolation)
    MEKO_DATAPACK_FRONTDESK: str = Field(
        default="318fdc74-eb15-4cf4-9be5-57b5820b3264",
        description="Datapack ID for cp-frontdesk"
    )
    MEKO_DATAPACK_DISPATCH: str = Field(
        default="cdb3987f-b677-495f-8d87-01999c3f9b91",
        description="Datapack ID for cp-dispatch"
    )
    
    # Coding agent datapack ID (STRICTLY FORBIDDEN to runtime product agents)
    FORBIDDEN_DEV_DATAPACK_ID: str = "8adfbdbc-8785-4bf0-b9dd-cd2adc8cd901"

    # LLM Settings
    LLM_PROVIDER: str = "mock"  # 'mock' or 'ollama'
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3.2:3b"

    # Demo Staff Authentication (Stage D Security)
    # Configured exclusively via environment variables; never hardcode tokens in Python source
    DEMO_STAFF_TOKENS: str = Field(
        default="",
        description="Demo staff authentication tokens mapping (token:reviewer_id:reviewer_role,... or JSON)"
    )

    # Demo Student Authentication (Stage H Identity)
    DEMO_STUDENT_TOKENS: str = Field(
        default="",
        description="Demo student authentication tokens mapping (token:student_id:name:email,... or JSON)"
    )

    model_config = SettingsConfigDict(
        env_file=[
            ".env",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
        ],
        extra="ignore"
    )

settings = Settings()

# Server-side allowlist for runtime agents
AGENT_DATAPACK_MAP: Dict[str, str] = {
    "frontdesk": settings.MEKO_DATAPACK_FRONTDESK,
    "dispatch": settings.MEKO_DATAPACK_DISPATCH,
}

def validate_agent_datapack(agent_role: str, datapack_id: str) -> bool:
    """Enforce strict server-side datapack allowlist per agent."""
    if datapack_id == settings.FORBIDDEN_DEV_DATAPACK_ID:
        raise PermissionError(
            f"Security Violation: Agent '{agent_role}' attempted to access forbidden coding datapack 'campuspulse-build'."
        )
    allowed_id = AGENT_DATAPACK_MAP.get(agent_role)
    if not allowed_id or allowed_id != datapack_id:
        raise PermissionError(
            f"Access Denied: Agent '{agent_role}' is not authorized to access datapack '{datapack_id}'. Allowed: '{allowed_id}'."
        )
    return True

def redact_sensitive_data(payload: dict) -> dict:
    """Recursively redact API keys, tokens, and authorization headers from logs."""
    redacted = {}
    for k, v in payload.items():
        if any(secret_term in k.lower() for secret_term in ["token", "key", "auth", "secret", "password"]):
            redacted[k] = "[REDACTED]"
        elif isinstance(v, dict):
            redacted[k] = redact_sensitive_data(v)
        elif isinstance(v, str) and "mko_tkn_" in v:
            redacted[k] = "[REDACTED_MEKO_TOKEN]"
        else:
            redacted[k] = v
    return redacted
