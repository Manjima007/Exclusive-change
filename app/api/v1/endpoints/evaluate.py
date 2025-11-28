"""
Flag Evaluation Endpoints.

This module provides high-performance endpoints for evaluating feature flags.
These endpoints are used by SDKs and client applications.

Authentication: API Key (X-API-Key header)

Endpoints:
    POST /evaluate       - Evaluate a single flag
    POST /evaluate/bulk  - Evaluate multiple flags
    POST /evaluate/all   - Evaluate all flags for a user
    GET  /config         - Get all flags for SDK bootstrap
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from app.api.deps import APIKey, Cache, DatabaseSession, EvaluatorDep, EnvironmentKey
from app.cache.redis import RedisCache
from app.core.security import APIKeyContext
from app.crud.crud_flag import crud_flag
from app.schemas.evaluate import (
    BulkEvaluationResult,
    EvaluateAllRequest,
    EvaluateAllResponse,
    EvaluateBulkRequest,
    EvaluateBulkResponse,
    EvaluateFlagRequest,
    EvaluateFlagResponse,
)
from app.schemas.flag import FlagConfigItem, FlagConfigResponse
from app.services.evaluator import FlagEvaluator

router = APIRouter(prefix="/evaluate", tags=["evaluate"])


@router.post(
    "",
    response_model=EvaluateFlagResponse,
    summary="Evaluate a single feature flag",
    description="""
    Evaluate a feature flag for a specific user.
    
    The evaluation uses deterministic hashing (MD5) to ensure the same user
    always gets the same result for a given flag.
    
    **Evaluation Logic:**
    1. If flag is disabled → returns false
    2. If flag is not found → returns default_value
    3. Compute: hash = MD5(user_id + flag_key) % 100
    4. If hash < rollout_percentage → returns true
    5. Otherwise → returns false
    """,
)
async def evaluate_flag(
    request: EvaluateFlagRequest,
    evaluator: EvaluatorDep,
) -> EvaluateFlagResponse:
    """
    Evaluate a single feature flag.
    
    - **flag_key**: The flag to evaluate
    - **context.user_id**: User identifier for consistent hashing
    - **default_value**: Value to return if flag not found (default: false)
    """
    result = await evaluator.evaluate(
        flag_key=request.flag_key,
        user_id=request.context.user_id,
        default_value=request.default_value,
    )
    
    return EvaluateFlagResponse(
        flag_key=result.flag_key,
        value=result.value,
        reason=result.reason.value,
    )


@router.post(
    "/bulk",
    response_model=EvaluateBulkResponse,
    summary="Evaluate multiple feature flags",
    description="""
    Evaluate multiple feature flags for a user in a single request.
    
    More efficient than calling the single evaluation endpoint multiple times.
    Useful when you need to check several flags at once.
    """,
)
async def evaluate_bulk(
    request: EvaluateBulkRequest,
    evaluator: EvaluatorDep,
) -> EvaluateBulkResponse:
    """
    Evaluate multiple flags at once.
    
    - **flag_keys**: List of flags to evaluate (max 100)
    - **context.user_id**: User identifier
    """
    results = await evaluator.evaluate_bulk(
        flag_keys=request.flag_keys,
        user_id=request.context.user_id,
        default_value=request.default_value,
    )
    
    return EvaluateBulkResponse(
        results=[
            BulkEvaluationResult(
                flag_key=r.flag_key,
                value=r.value,
                reason=r.reason.value,
            )
            for r in results
        ],
        evaluated_at=datetime.now(timezone.utc),
    )


@router.post(
    "/all",
    response_model=EvaluateAllResponse,
    summary="Evaluate all flags for a user",
    description="""
    Evaluate all active feature flags for a user.
    
    Returns a map of flag_key → boolean value for all active flags.
    Useful for SDK initialization to get the complete flag state.
    """,
)
async def evaluate_all(
    request: EvaluateAllRequest,
    evaluator: EvaluatorDep,
    environment: EnvironmentKey,
) -> EvaluateAllResponse:
    """
    Evaluate all flags for a user.
    
    Returns all active flags with their evaluated values.
    """
    flags = await evaluator.evaluate_all(request.context.user_id)
    
    return EvaluateAllResponse(
        flags=flags,
        environment=environment,
        evaluated_at=datetime.now(timezone.utc),
    )


# =============================================================================
# SDK Configuration Endpoint (separate from /evaluate prefix)
# =============================================================================

config_router = APIRouter(prefix="/sdk", tags=["config"])


@config_router.get(
    "/config",
    response_model=FlagConfigResponse,
    summary="Get flag configuration for SDK",
    description="""
    Get the full flag configuration for SDK initialization.
    
    Returns all active flags with their rollout percentages.
    SDKs can use this to bootstrap and then evaluate flags locally.
    
    **Note:** This returns raw flag data, not evaluated values.
    For evaluated values, use the /evaluate/all endpoint.
    """,
)
async def get_flag_config(
    api_key: APIKey,
    db: DatabaseSession,
    cache: Cache,
) -> FlagConfigResponse:
    """
    Get flag configuration for SDK bootstrap.
    
    Returns all active flags for the tenant/environment.
    """
    tenant_id = api_key.tenant_id
    environment = api_key.environment_key
    
    # Try cache first
    cached = await cache.get_flags(tenant_id, environment)
    if cached:
        flags_data = cached.get("flags", {})
        return FlagConfigResponse(
            flags=[
                FlagConfigItem(
                    key=k,
                    rollout_percentage=v.get("rollout_percentage", 0),
                    is_enabled=v.get("is_enabled", False),
                )
                for k, v in flags_data.items()
            ],
            environment=environment,
            generated_at=datetime.fromisoformat(cached.get("cached_at", datetime.now(timezone.utc).isoformat())),
        )
    
    # Cache miss - get from database
    flags = await crud_flag.get_active_flags(db, tenant_id)
    
    # Cache the results
    flags_list = [
        {
            "key": f.key,
            "rollout_percentage": f.rollout_percentage,
            "is_enabled": f.is_enabled,
            "status": f.status,
        }
        for f in flags
    ]
    await cache.set_flags(tenant_id, environment, flags_list)
    
    return FlagConfigResponse(
        flags=[
            FlagConfigItem(
                key=f.key,
                rollout_percentage=f.rollout_percentage,
                is_enabled=f.is_enabled,
            )
            for f in flags
        ],
        environment=environment,
        generated_at=datetime.now(timezone.utc),
    )
