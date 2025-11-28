"""
Security Module: JWT and API Key Authentication.

This module provides authentication mechanisms for:
    1. Management API: JWT tokens from Supabase Auth
    2. Evaluation API: API Keys for SDK access

Security Design:
    - JWT tokens are validated against Supabase's secret
    - API keys are hashed with SHA-256 before storage
    - All auth functions are async for non-blocking I/O
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, InvalidAPIKeyError
from app.crud.crud_tenant import crud_api_key
from app.db.session import get_db
from app.models.tenant import APIKey

logger = logging.getLogger(__name__)

# FastAPI security scheme for Bearer tokens
bearer_scheme = HTTPBearer(auto_error=False)


# =============================================================================
# JWT Token Validation (Management API)
# =============================================================================

class JWTPayload:
    """
    Parsed JWT token payload.
    
    Attributes:
        sub: Subject (Supabase user ID).
        email: User's email address.
        exp: Token expiration timestamp.
        aud: Audience claim.
        role: User's role (e.g., "authenticated").
    """
    
    def __init__(self, payload: dict[str, Any]) -> None:
        self.sub: str = payload.get("sub", "")
        self.email: str | None = payload.get("email")
        self.exp: int = payload.get("exp", 0)
        self.aud: str = payload.get("aud", "")
        self.role: str = payload.get("role", "")
        self.raw = payload
    
    @property
    def user_id(self) -> uuid.UUID:
        """Get the user ID as UUID."""
        return uuid.UUID(self.sub)


def decode_jwt_token(token: str) -> JWTPayload:
    """
    Decode and validate a JWT token from Supabase Auth.
    
    Args:
        token: The JWT token string.
    
    Returns:
        JWTPayload with decoded claims.
    
    Raises:
        AuthenticationError: If token is invalid or expired.
    """
    from datetime import timedelta
    
    try:
        # Supabase uses HS256 with the JWT secret (raw string, not base64-decoded)
        secret = settings.SUPABASE_JWT_SECRET
        
        # Use a large leeway to handle clock skew between client and Supabase servers
        # Also disable iat verification to avoid "not yet valid" errors
        decode_options = {
            "verify_aud": True,
            "verify_iat": False,  # Disable iat check to handle clock skew
            "require": ["exp", "sub"],  # Only require exp and sub
        }
        
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
                options=decode_options,
                leeway=timedelta(hours=24),  # Large leeway for clock skew
            )
            logger.debug("JWT decoded successfully")
            return JWTPayload(payload)
        except jwt.InvalidSignatureError as e:
            logger.warning(f"JWT signature verification failed: {e}")
            raise
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationError(
            message="Token has expired",
            error_code="TOKEN_EXPIRED",
        )
    except jwt.InvalidAudienceError:
        raise AuthenticationError(
            message="Invalid token audience",
            error_code="INVALID_AUDIENCE",
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise AuthenticationError(
            message="Invalid token",
            error_code="INVALID_TOKEN",
        )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> JWTPayload:
    """
    FastAPI dependency to get the current authenticated user.
    
    Extracts and validates the JWT token from the Authorization header.
    
    Usage:
        @router.get("/me")
        async def get_profile(user: JWTPayload = Depends(get_current_user)):
            return {"user_id": str(user.user_id), "email": user.email}
    
    Args:
        credentials: Bearer token from Authorization header.
    
    Returns:
        JWTPayload with user information.
    
    Raises:
        HTTPException: If authentication fails.
    """
    # Development mode bypass for testing
    if settings.APP_ENV == "development" and credentials is not None:
        if credentials.credentials == "dev-token":
            # Return a mock user for development testing
            return JWTPayload({
                "sub": "00000000-0000-0000-0000-000000000001",
                "email": "dev@example.com",
                "exp": 9999999999,
                "aud": "authenticated",
                "role": "authenticated",
            })
    
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        return decode_jwt_token(credentials.credentials)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )


# =============================================================================
# API Key Authentication (Evaluation API)
# =============================================================================

class APIKeyContext:
    """
    Context from a validated API key.
    
    Provides tenant and environment information for the request.
    
    Attributes:
        api_key: The validated APIKey model.
        tenant_id: Tenant UUID from the key.
        environment_id: Environment UUID from the key.
        environment_key: Environment key (e.g., "production").
    """
    
    def __init__(self, api_key: APIKey) -> None:
        self.api_key = api_key
        self.tenant_id = api_key.tenant_id
        self.environment_id = api_key.environment_id
        self.environment_key = api_key.environment.key
        self.tenant_slug = api_key.tenant.slug


async def validate_api_key(
    db: AsyncSession,
    raw_key: str,
) -> APIKeyContext:
    """
    Validate an API key and return the context.
    
    Args:
        db: Database session.
        raw_key: The raw API key string.
    
    Returns:
        APIKeyContext with tenant/environment info.
    
    Raises:
        InvalidAPIKeyError: If key is invalid or inactive.
    """
    # Hash the key for lookup
    key_hash = APIKey.hash_key(raw_key)
    
    # Look up the key
    api_key = await crud_api_key.get_by_hash(db, key_hash)
    
    if api_key is None:
        logger.warning(f"Invalid API key attempted: {raw_key[:12]}...")
        raise InvalidAPIKeyError()
    
    if not api_key.is_active:
        logger.warning(f"Inactive API key used: {api_key.key_prefix}")
        raise InvalidAPIKeyError(message="API key has been revoked")
    
    if not api_key.tenant.is_active:
        logger.warning(f"API key for inactive tenant: {api_key.tenant.slug}")
        raise InvalidAPIKeyError(message="Tenant account is inactive")
    
    # Update last used timestamp (fire and forget)
    await crud_api_key.update_last_used(db, api_key)
    
    return APIKeyContext(api_key)


async def get_api_key_context(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> APIKeyContext:
    """
    FastAPI dependency to validate API key from header.
    
    Accepts the API key from either:
        - X-API-Key header (preferred)
        - Authorization header with "Bearer" prefix
    
    Usage:
        @router.post("/evaluate")
        async def evaluate(
            context: APIKeyContext = Depends(get_api_key_context),
        ):
            tenant_id = context.tenant_id
            # ...
    
    Args:
        x_api_key: API key from X-API-Key header.
        authorization: Authorization header value.
        db: Database session.
    
    Returns:
        APIKeyContext with tenant/environment information.
    
    Raises:
        HTTPException: If API key is missing or invalid.
    """
    # Try X-API-Key header first
    raw_key = x_api_key
    
    # Fallback to Authorization header
    if raw_key is None and authorization:
        if authorization.startswith("Bearer "):
            raw_key = authorization[7:]
        else:
            raw_key = authorization
    
    if raw_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide via X-API-Key header.",
        )
    
    try:
        return await validate_api_key(db, raw_key)
    except InvalidAPIKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )


# =============================================================================
# Tenant Context Dependencies
# =============================================================================

class TenantContext:
    """
    Combined context for authenticated requests.
    
    Used by the Management API to track both user and tenant.
    """
    
    def __init__(
        self,
        user: JWTPayload,
        tenant_id: uuid.UUID,
    ) -> None:
        self.user = user
        self.user_id = user.user_id
        self.user_email = user.email
        self.tenant_id = tenant_id


# TODO: Implement proper tenant resolution from JWT claims or separate lookup
# For now, we'll need to pass tenant_id explicitly or use a header

async def get_tenant_context(
    user: Annotated[JWTPayload, Depends(get_current_user)],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> TenantContext:
    """
    Get the tenant context from authenticated request.
    
    The tenant ID can be provided via X-Tenant-ID header.
    In production, you might store tenant association in user metadata.
    
    Args:
        user: Authenticated user from JWT.
        x_tenant_id: Tenant ID from header.
    
    Returns:
        TenantContext with user and tenant info.
    
    Raises:
        HTTPException: If tenant ID is missing.
    """
    if x_tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header required",
        )
    
    try:
        tenant_id = uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format",
        )
    
    return TenantContext(user, tenant_id)
