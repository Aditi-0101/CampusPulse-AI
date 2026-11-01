from typing import Optional
from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    """Login request payload containing user-configured access token."""
    credential: str = Field(..., description="Configured student or staff access credential", min_length=1)

class UserSession(BaseModel):
    """Authenticated user profile representation."""
    user_id: str = Field(..., description="Unique user or staff identifier")
    role: str = Field(..., description="Assigned role: STUDENT, NOC_SUPERVISOR, CAMPUS_ADMIN, VICE_CHANCELLOR, READ_ONLY")
    name: str = Field(..., description="Display name")
    email: Optional[str] = Field(None, description="Email address if available")
    portal: str = Field(..., description="Assigned portal destination: student, admin, or vc")
    token_type: str = Field(default="staff", description="Credential type: student or staff")

class LoginResponse(BaseModel):
    """Response returned upon successful authentication."""
    status: str = Field(default="authenticated")
    user: UserSession
    redirect_url: str = Field(..., description="Target portal destination based on authenticated role")

class UserProfileResponse(BaseModel):
    """User profile returned by /api/v1/auth/me."""
    user_id: str
    name: str
    role: str
    email: Optional[str] = None
    portal: str

class LogoutResponse(BaseModel):
    """Response returned upon session logout."""
    status: str = Field(default="logged_out")
    detail: str = Field(default="Session terminated successfully.")
