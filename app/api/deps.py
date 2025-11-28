"""
API Dependencies.

This module provides FastAPI dependencies for:
    - Database session injection
    - Authentication (JWT and API Key)
    - Service layer injection
    - Cache access

Dependencies are designed for easy testing and mocking.
"""

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import RedisCache, cache, get_cache
from app.core.security import (
    APIKeyContext,
    JWTPayload,
    TenantContext,
    get_api_key_context,
    get_current_user,
    get_tenant_context,
)
from app.db.session import DBSession, get_db
from app.services.evaluator import FlagEvaluator
from app.services.flag_service import FlagService


# =============================================================================
# Type Aliases for Cleaner Dependency Injection
# =============================================================================

# Database session dependency
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]

# Cache dependency
Cache = Annotated[RedisCache, Depends(get_cache)]

# Authentication dependencies
CurrentUser = Annotated[JWTPayload, Depends(get_current_user)]
APIKey = Annotated[APIKeyContext, Depends(get_api_key_context)]
Tenant = Annotated[TenantContext, Depends(get_tenant_context)]


# =============================================================================
# Service Dependencies
# =============================================================================

async def get_flag_service(
    db: DatabaseSession,
    cache: Cache,
    tenant: Tenant,
) -> FlagService:
    """
    Dependency to get the FlagService for Management API.
    
    Combines database, cache, and tenant context.
    
    Usage:
        @router.post("/flags")
        async def create_flag(
            flag_service: FlagService = Depends(get_flag_service),
        ):
            ...
    """
    return FlagService(db, cache, tenant.tenant_id)


async def get_evaluator_for_api_key(
    db: DatabaseSession,
    cache: Cache,
    api_key: APIKey,
) -> FlagEvaluator:
    """
    Dependency to get the FlagEvaluator for Evaluation API.
    
    Uses API key context for tenant resolution.
    
    Usage:
        @router.post("/evaluate")
        async def evaluate_flag(
            evaluator: FlagEvaluator = Depends(get_evaluator_for_api_key),
        ):
            ...
    """
    return FlagEvaluator(db, cache, api_key.tenant_id)


# Type aliases for service dependencies
FlagServiceDep = Annotated[FlagService, Depends(get_flag_service)]
EvaluatorDep = Annotated[FlagEvaluator, Depends(get_evaluator_for_api_key)]


# =============================================================================
# Utility Dependencies
# =============================================================================

async def get_tenant_id_from_api_key(
    api_key: APIKey,
) -> uuid.UUID:
    """Extract tenant ID from API key context."""
    return api_key.tenant_id


async def get_environment_key_from_api_key(
    api_key: APIKey,
) -> str:
    """Extract environment key from API key context."""
    return api_key.environment_key


TenantID = Annotated[uuid.UUID, Depends(get_tenant_id_from_api_key)]
EnvironmentKey = Annotated[str, Depends(get_environment_key_from_api_key)]
