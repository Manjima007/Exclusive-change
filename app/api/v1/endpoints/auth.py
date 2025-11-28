"""
Authentication Endpoints.

These endpoints handle user authentication via Supabase Auth.
They provide a simple wrapper around Supabase's auth API.

Flow:
    1. User signs up with email/password → Supabase creates user
    2. User signs in → Gets JWT token
    3. User uses JWT token in Authorization header for Management API

Note: 
    - Supabase handles email verification, password reset, etc.
    - We just validate the JWT tokens they issue
"""

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.core.security import JWTPayload, get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])


# =============================================================================
# Request/Response Schemas
# =============================================================================

class SignUpRequest(BaseModel):
    """Request body for user registration."""
    
    email: EmailStr = Field(
        ...,
        description="User's email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Password (min 8 characters)",
        examples=["SecurePass123!"],
    )
    full_name: str | None = Field(
        default=None,
        max_length=100,
        description="User's full name (optional)",
        examples=["John Doe"],
    )


class SignInRequest(BaseModel):
    """Request body for user login."""
    
    email: EmailStr = Field(
        ...,
        description="User's email address",
    )
    password: str = Field(
        ...,
        description="User's password",
    )


class AuthResponse(BaseModel):
    """Response after successful authentication."""
    
    access_token: str = Field(
        description="JWT token for API authentication",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')",
    )
    expires_in: int = Field(
        description="Token expiry in seconds",
    )
    expires_at: datetime = Field(
        description="Token expiry timestamp",
    )
    refresh_token: str = Field(
        description="Token to refresh the access token",
    )
    user: dict[str, Any] = Field(
        description="User information",
    )


class RefreshRequest(BaseModel):
    """Request body for token refresh."""
    
    refresh_token: str = Field(
        ...,
        description="Refresh token from sign in response",
    )


class MessageResponse(BaseModel):
    """Simple message response."""
    
    message: str
    success: bool = True


# =============================================================================
# Helper Functions
# =============================================================================

async def _supabase_auth_request(
    endpoint: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Make a request to Supabase Auth API.
    
    Args:
        endpoint: Auth endpoint (e.g., "signup", "token")
        payload: Request body
        
    Returns:
        Response JSON
        
    Raises:
        HTTPException: If request fails
    """
    url = f"{settings.SUPABASE_URL}/auth/v1/{endpoint}"
    
    headers = {
        "apikey": settings.SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        
        if response.status_code >= 400:
            error_data = response.json()
            error_msg = error_data.get("error_description") or error_data.get("msg") or "Authentication failed"
            
            if response.status_code == 400:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg,
                )
            elif response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=error_msg,
                )
            elif response.status_code == 422:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=error_msg,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authentication service error",
                )
        
        return response.json()


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="""
    Create a new user account with email and password.
    
    After signup:
    - User receives a confirmation email (if enabled in Supabase)
    - User can immediately sign in (depending on Supabase settings)
    - Use the returned access_token for API requests
    """,
)
async def sign_up(request: SignUpRequest) -> AuthResponse:
    """Register a new user."""
    
    # Build user metadata
    user_metadata = {}
    if request.full_name:
        user_metadata["full_name"] = request.full_name
    
    payload = {
        "email": request.email,
        "password": request.password,
        "data": user_metadata,
    }
    
    data = await _supabase_auth_request("signup", payload)
    
    # Check if email confirmation is required
    if "access_token" not in data:
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail="Please check your email to confirm your account",
        )
    
    return AuthResponse(
        access_token=data["access_token"],
        token_type="bearer",
        expires_in=data.get("expires_in", 3600),
        expires_at=datetime.fromtimestamp(data.get("expires_at", 0), tz=timezone.utc),
        refresh_token=data.get("refresh_token", ""),
        user=data.get("user", {}),
    )


@router.post(
    "/signin",
    response_model=AuthResponse,
    summary="Sign in with email and password",
    description="""
    Authenticate with email and password to get an access token.
    
    Use the returned access_token in the Authorization header:
    ```
    Authorization: Bearer <access_token>
    ```
    """,
)
async def sign_in(request: SignInRequest) -> AuthResponse:
    """Sign in and get access token."""
    
    payload = {
        "email": request.email,
        "password": request.password,
    }
    
    data = await _supabase_auth_request("token?grant_type=password", payload)
    
    return AuthResponse(
        access_token=data["access_token"],
        token_type="bearer",
        expires_in=data.get("expires_in", 3600),
        expires_at=datetime.fromtimestamp(data.get("expires_at", 0), tz=timezone.utc),
        refresh_token=data.get("refresh_token", ""),
        user=data.get("user", {}),
    )


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Refresh access token",
    description="""
    Use a refresh token to get a new access token.
    
    Call this when your access token expires to get a new one
    without requiring the user to sign in again.
    """,
)
async def refresh_token(request: RefreshRequest) -> AuthResponse:
    """Refresh the access token."""
    
    url = f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=refresh_token"
    
    headers = {
        "apikey": settings.SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json={"refresh_token": request.refresh_token},
            headers=headers,
        )
        
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )
        
        data = response.json()
    
    return AuthResponse(
        access_token=data["access_token"],
        token_type="bearer",
        expires_in=data.get("expires_in", 3600),
        expires_at=datetime.fromtimestamp(data.get("expires_at", 0), tz=timezone.utc),
        refresh_token=data.get("refresh_token", ""),
        user=data.get("user", {}),
    )


@router.post(
    "/signout",
    response_model=MessageResponse,
    summary="Sign out",
    description="Invalidate the current session.",
)
async def sign_out() -> MessageResponse:
    """Sign out (client-side token removal is sufficient)."""
    # Supabase JWT tokens are stateless, so signing out is mainly
    # about the client discarding the token
    return MessageResponse(
        message="Successfully signed out. Please discard your tokens.",
        success=True,
    )


@router.get(
    "/me",
    summary="Get current user",
    description="Get the currently authenticated user's information from the JWT token.",
)
async def get_current_user_info(
    user: JWTPayload = Depends(get_current_user),
) -> dict[str, Any]:
    """Get current user info from JWT."""
    return {
        "user_id": str(user.user_id),
        "email": user.email,
        "role": user.role,
        "aud": user.aud,
    }


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request password reset",
    description="Send a password reset email to the user.",
)
async def forgot_password(email: EmailStr) -> MessageResponse:
    """Request a password reset email."""
    
    url = f"{settings.SUPABASE_URL}/auth/v1/recover"
    
    headers = {
        "apikey": settings.SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json={"email": email},
            headers=headers,
        )
        
        # Always return success to prevent email enumeration
        if response.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send reset email",
            )
    
    return MessageResponse(
        message="If an account exists with this email, a reset link has been sent.",
        success=True,
    )
