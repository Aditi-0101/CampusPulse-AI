import logging
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status

from backend.app.core.config import settings
from backend.app.core.auth import (
    authenticate_credential,
    create_session_token,
    get_optional_session_user,
    get_current_user,
    UserSession,
)
from backend.app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserProfileResponse,
    LogoutResponse,
)

logger = logging.getLogger("campuspulse.api.auth")

router = APIRouter()

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate user credential and establish secure HttpOnly session",
    description="Validates configured student or staff token, resolves identity on server, sets HttpOnly cookie."
)
async def login(
    payload: LoginRequest,
    response: Response,
):
    """
    Server-side authentication endpoint.
    Derives role and identity on backend; never trusts role supplied by client.
    Sets HttpOnly, SameSite-protected cookie.
    """
    user_session = authenticate_credential(payload.credential)
    if not user_session:
        # Generic error message without disclosing which credentials or roles exist
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Invalid or unrecognized access credential."
        )

    # Generate cryptographically signed session token
    session_token = create_session_token(user_session)

    # Cookie security attributes
    # Cookie security attributes: use SameSite=None and Secure=True in production/HTTPS
    is_prod = (settings.ENVIRONMENT.lower() == "production") or bool(
        settings.FRONTEND_URL and settings.FRONTEND_URL.startswith("https://")
    )
    cookie_samesite = "none" if is_prod else "lax"
    cookie_secure = True if is_prod else False
    
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        max_age=getattr(settings, "SESSION_MAX_AGE_SECONDS", 86400),
        httponly=True,
        samesite=cookie_samesite,
        secure=cookie_secure,
        path="/",
    )

    redirect_target = f"/{user_session.portal}"

    logger.info(f"User '{user_session.user_id}' authenticated successfully with role '{user_session.role}'. Redirect -> {redirect_target}")

    return LoginResponse(
        status="authenticated",
        user=user_session,
        redirect_url=redirect_target,
    )

@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get currently authenticated user session profile",
    description="Returns authenticated user identity derived from validated HttpOnly session cookie."
)
async def get_session_profile(
    request: Request,
    current_user: UserSession = Depends(get_current_user),
):
    """Returns authenticated profile or raises 401 if unauthenticated."""
    return UserProfileResponse(
        user_id=current_user.user_id,
        name=current_user.name,
        role=current_user.role,
        email=current_user.email,
        portal=current_user.portal,
    )

@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Log out and invalidate session cookie",
    description="Clears the HttpOnly session cookie from the client."
)
async def logout(
    response: Response,
):
    """Clears the HttpOnly session cookie."""
    is_prod = (settings.ENVIRONMENT.lower() == "production") or bool(
        settings.FRONTEND_URL and settings.FRONTEND_URL.startswith("https://")
    )
    cookie_samesite = "none" if is_prod else "lax"
    cookie_secure = True if is_prod else False

    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=cookie_samesite,
        secure=cookie_secure,
    )
    return LogoutResponse()
