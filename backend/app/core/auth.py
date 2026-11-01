import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Dict, Optional, Set
from pydantic import BaseModel
from fastapi import HTTPException, Security, status, Request
from fastapi.security import APIKeyHeader

from backend.app.core.config import settings
from backend.app.schemas.auth import UserSession

logger = logging.getLogger("campuspulse.auth")

staff_token_header = APIKeyHeader(name="X-Staff-Token", auto_error=False)
student_token_header = APIKeyHeader(name="X-Student-Token", auto_error=False)

# Disallowed AI identifiers to prevent self-approval or automated authorization
AI_AGENT_IDENTIFIERS: Set[str] = {
    "frontdesk", "dispatch", "technician", "curator",
    "product_agent", "product_agent:frontdesk", "product_agent:dispatch",
    "coding_agent", "antigravity", "ai_agent", "swarm"
}

# Roles authorized to make binding operational approval/rejection decisions
AUTHORIZED_APPROVAL_ROLES: Set[str] = {
    "NOC_SUPERVISOR",
    "CAMPUS_ADMIN",
    "NETWORK_ENGINEER",
    "FACILITIES_MANAGER",
    "VICE_CHANCELLOR",
}

class StaffIdentity(BaseModel):
    """Authenticated staff member identity resolved server-side from demo staff token."""
    reviewer_id: str
    reviewer_role: str

class StudentIdentity(BaseModel):
    """Authenticated student identity resolved server-side from demo student token."""
    student_id: str
    name: str
    email: str


# =============================================================================
# Session Token Utilities (Signed HttpOnly Cookies)
# =============================================================================

def create_session_token(session: UserSession) -> str:
    """Create a tamper-proof signed session token using HMAC-SHA256."""
    payload = {
        "user_id": session.user_id,
        "role": session.role,
        "name": session.name,
        "email": session.email or "",
        "portal": session.portal,
        "token_type": session.token_type,
        "exp": int(time.time()) + getattr(settings, "SESSION_MAX_AGE_SECONDS", 86400),
    }
    raw_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_bytes).decode("utf-8").rstrip("=")
    sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"

def verify_session_token(token_str: str) -> Optional[UserSession]:
    """Verify HMAC signature and expiry of a session token."""
    if not token_str or "." not in token_str:
        return None
    try:
        parts = token_str.split(".", 1)
        b64_payload, provided_sig = parts[0], parts[1]
        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig.encode("utf-8"), provided_sig.encode("utf-8")):
            return None

        padded = b64_payload + "=" * (-len(b64_payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
        if data.get("exp", 0) < time.time():
            return None

        return UserSession(
            user_id=data["user_id"],
            role=data["role"],
            name=data["name"],
            email=data.get("email", ""),
            portal=data["portal"],
            token_type=data.get("token_type", "staff"),
        )
    except Exception as e:
        logger.debug(f"Session token verification failed: {e}")
        return None


# =============================================================================
# Staff Token Mapping and Lookup
# =============================================================================

def parse_staff_token_map(raw_config: str) -> Dict[str, StaffIdentity]:
    token_map: Dict[str, StaffIdentity] = {}
    cleaned = (raw_config or "").strip()
    if not cleaned:
        return token_map

    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            data = json.loads(cleaned)
            for token, info in data.items():
                if isinstance(info, dict) and "reviewer_id" in info and "reviewer_role" in info:
                    token_map[str(token).strip()] = StaffIdentity(
                        reviewer_id=str(info["reviewer_id"]).strip(),
                        reviewer_role=str(info["reviewer_role"]).strip().upper()
                    )
            return token_map
        except Exception as e:
            logger.warning(f"Failed to parse DEMO_STAFF_TOKENS as JSON; falling back to delimited format: {e}")

    for entry in cleaned.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) >= 3:
            token = parts[0].strip()
            rev_id = parts[1].strip()
            rev_role = parts[2].strip().upper()
            if token and rev_id and rev_role:
                token_map[token] = StaffIdentity(reviewer_id=rev_id, reviewer_role=rev_role)
    return token_map

def get_demo_staff_token_map() -> Dict[str, StaffIdentity]:
    raw = getattr(settings, "DEMO_STAFF_TOKENS", "") or os.environ.get("DEMO_STAFF_TOKENS", "")
    return parse_staff_token_map(raw)

def find_staff_by_token(provided_token: str) -> Optional[StaffIdentity]:
    if not provided_token or not provided_token.strip():
        return None

    token_map = get_demo_staff_token_map()
    provided_bytes = provided_token.strip().encode("utf-8")
    matched_identity: Optional[StaffIdentity] = None

    for valid_token, identity in token_map.items():
        valid_bytes = valid_token.encode("utf-8")
        if hmac.compare_digest(valid_bytes, provided_bytes):
            matched_identity = identity
            break

    return matched_identity


# =============================================================================
# Student Token Mapping and Lookup
# =============================================================================

def parse_student_token_map(raw_config: str) -> Dict[str, StudentIdentity]:
    token_map: Dict[str, StudentIdentity] = {}
    cleaned = (raw_config or "").strip()
    if not cleaned:
        return token_map

    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            data = json.loads(cleaned)
            for token, info in data.items():
                if isinstance(info, dict) and "student_id" in info:
                    token_map[str(token).strip()] = StudentIdentity(
                        student_id=str(info["student_id"]).strip(),
                        name=str(info.get("name", "Student")).strip(),
                        email=str(info.get("email", "")).strip(),
                    )
            return token_map
        except Exception as e:
            logger.warning(f"Failed to parse DEMO_STUDENT_TOKENS as JSON: {e}")

    for entry in cleaned.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) >= 2:
            token = parts[0].strip()
            std_id = parts[1].strip()
            name = parts[2].strip() if len(parts) >= 3 else "Verified Student"
            email = parts[3].strip() if len(parts) >= 4 else ""
            if token and std_id:
                token_map[token] = StudentIdentity(student_id=std_id, name=name, email=email)
    return token_map

def get_demo_student_token_map() -> Dict[str, StudentIdentity]:
    raw = getattr(settings, "DEMO_STUDENT_TOKENS", "") or os.environ.get("DEMO_STUDENT_TOKENS", "")
    return parse_student_token_map(raw)

def find_student_by_token(provided_token: str) -> Optional[StudentIdentity]:
    if not provided_token or not provided_token.strip():
        return None

    token_map = get_demo_student_token_map()
    provided_bytes = provided_token.strip().encode("utf-8")
    matched_identity: Optional[StudentIdentity] = None

    for valid_token, identity in token_map.items():
        valid_bytes = valid_token.encode("utf-8")
        if hmac.compare_digest(valid_bytes, provided_bytes):
            matched_identity = identity
            break

    return matched_identity


# =============================================================================
# Unified Credential Authenticator (for Login Endpoint)
# =============================================================================

def authenticate_credential(credential: str) -> Optional[UserSession]:
    """
    Authenticate against configured student or staff credentials.
    Derives user identity and role strictly on the backend.
    Never trusts role supplied by frontend.
    """
    clean = (credential or "").strip()
    if not clean:
        return None

    # 1. Try student token lookup
    student = find_student_by_token(clean)
    if student:
        return UserSession(
            user_id=student.student_id,
            role="STUDENT",
            name=student.name,
            email=student.email,
            portal="student",
            token_type="student",
        )

    # 2. Try staff token lookup
    staff = find_staff_by_token(clean)
    if staff:
        clean_id = staff.reviewer_id.lower()
        clean_role = staff.reviewer_role.lower()
        if any(agent_id in clean_id for agent_id in AI_AGENT_IDENTIFIERS) or any(agent_id in clean_role for agent_id in AI_AGENT_IDENTIFIERS):
            logger.warning(f"Login denied: AI agent identifier '{staff.reviewer_id}' cannot login as human user.")
            return None

        role = staff.reviewer_role.upper()
        # Derive human-friendly display name
        if role == "VICE_CHANCELLOR":
            name = "Vice-Chancellor's Office"
            portal = "vc"
        elif "supervisor" in clean_id:
            name = "NOC Supervisor"
            portal = "admin"
        elif "admin" in clean_id or "lead" in clean_id:
            name = "Campus Administrator"
            portal = "admin"
        elif "intern" in clean_id or role == "READ_ONLY":
            name = "Operations Auditor (Read-Only)"
            portal = "admin"
        else:
            name = staff.reviewer_id.replace("staff_", "").replace("_", " ").title()
            portal = "admin"

        return UserSession(
            user_id=staff.reviewer_id,
            role=role,
            name=name,
            email=f"{staff.reviewer_id}@campus.edu",
            portal=portal,
            token_type="staff",
        )

    return None


# =============================================================================
# Session Dependencies
# =============================================================================

async def get_optional_session_user(request: Request) -> Optional[UserSession]:
    """Retrieve verified UserSession from HttpOnly cookie if present."""
    if not request:
        return None
    cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_token:
        return verify_session_token(cookie_token)
    return None

async def get_current_user(
    request: Request,
    x_staff_token: Optional[str] = Security(staff_token_header),
    x_student_token: Optional[str] = Security(student_token_header),
) -> UserSession:
    """Enforce authenticated user via HttpOnly cookie or API headers."""
    session_user = await get_optional_session_user(request)
    if session_user:
        return session_user

    # Fallback to header tokens for direct API calls and tests
    if x_staff_token:
        staff = find_staff_by_token(x_staff_token)
        if staff:
            role = staff.reviewer_role.upper()
            portal = "vc" if role == "VICE_CHANCELLOR" else "admin"
            return UserSession(
                user_id=staff.reviewer_id,
                role=role,
                name=staff.reviewer_id,
                portal=portal,
                token_type="staff",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or unrecognized staff token.")

    if x_student_token:
        student = find_student_by_token(x_student_token)
        if student:
            return UserSession(
                user_id=student.student_id,
                role="STUDENT",
                name=student.name,
                email=student.email,
                portal="student",
                token_type="student",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or unrecognized student token.")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in or provide valid credentials."
    )


# =============================================================================
# Role-Specific Dependencies (Backend Protection)
# =============================================================================

async def get_current_staff(
    request: Request = None,
    x_staff_token: Optional[str] = Security(staff_token_header)
) -> StaffIdentity:
    """
    Authenticate staff member via HttpOnly cookie or X-Staff-Token header.
    Rejects students with 403 Forbidden.
    Rejects unauthenticated requests with 401 Unauthorized.
    """
    if request:
        session_user = await get_optional_session_user(request)
        if session_user:
            if session_user.role == "STUDENT":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Students are not authorized to access staff operations."
                )
            return StaffIdentity(reviewer_id=session_user.user_id, reviewer_role=session_user.role)

    if not x_staff_token or not x_staff_token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Missing 'X-Staff-Token' header."
        )

    staff = find_staff_by_token(x_staff_token)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Invalid or unrecognized staff token."
        )

    clean_id = staff.reviewer_id.lower()
    clean_role = staff.reviewer_role.lower()
    if any(agent_id in clean_id for agent_id in AI_AGENT_IDENTIFIERS) or any(agent_id in clean_role for agent_id in AI_AGENT_IDENTIFIERS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI agents are strictly forbidden from approving recommendations. A verified human staff member is required."
        )

    return staff

def verify_approval_permission(staff: StaffIdentity) -> None:
    """Enforce role permissions: only authorized operational roles may approve or reject."""
    normalized_role = (staff.reviewer_role or "").strip().upper()
    if normalized_role not in AUTHORIZED_APPROVAL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{staff.reviewer_role}' does not have permission to approve or reject grievances. "
                f"Authorized roles: {', '.join(sorted(AUTHORIZED_APPROVAL_ROLES))}."
            )
        )

async def get_current_vc(
    request: Request = None,
    staff: StaffIdentity = Security(get_current_staff)
) -> StaffIdentity:
    """
    Ensure the authenticated user specifically holds the VICE_CHANCELLOR role.
    Rejects non-VC staff with 403 Forbidden.
    """
    normalized_role = (staff.reviewer_role or "").strip().upper()
    if normalized_role != "VICE_CHANCELLOR":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Role '{staff.reviewer_role}' is not authorized for Vice-Chancellor operations."
        )
    return staff

async def get_current_student(
    request: Request = None,
    x_student_token: Optional[str] = Security(student_token_header)
) -> StudentIdentity:
    """
    Authenticate verified student via HttpOnly cookie or X-Student-Token header.
    Rejects staff members with 403 Forbidden.
    Rejects unauthenticated requests with 401 Unauthorized.
    """
    if request:
        session_user = await get_optional_session_user(request)
        if session_user:
            if session_user.role != "STUDENT":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Staff credentials cannot be used for student portal operations."
                )
            return StudentIdentity(
                student_id=session_user.user_id,
                name=session_user.name,
                email=session_user.email or "",
            )

    if not x_student_token or not x_student_token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student authentication required: Missing 'X-Student-Token' header."
        )

    student = find_student_by_token(x_student_token)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student authentication failed: Invalid or unrecognized student token."
        )

    return student

async def get_optional_current_student(
    request: Request = None,
    x_student_token: Optional[str] = Security(student_token_header)
) -> Optional[StudentIdentity]:
    """Optional student authentication (returns None if unauthenticated, raises 401 on bad token)."""
    if request:
        session_user = await get_optional_session_user(request)
        if session_user and session_user.role == "STUDENT":
            return StudentIdentity(
                student_id=session_user.user_id,
                name=session_user.name,
                email=session_user.email or "",
            )

    if not x_student_token or not x_student_token.strip():
        return None

    student = find_student_by_token(x_student_token)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student authentication failed: Invalid or unrecognized student token."
        )

    return student
