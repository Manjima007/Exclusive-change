"""
Flag Management Endpoints.

This module provides CRUD endpoints for feature flags.
All endpoints require JWT authentication and X-Tenant-ID header.

Endpoints:
    POST   /flags           - Create a new flag
    GET    /flags           - List all flags (paginated)
    GET    /flags/{key}     - Get a flag by key
    PATCH  /flags/{key}     - Update a flag
    DELETE /flags/{key}     - Delete a flag
    POST   /flags/{key}/toggle - Toggle flag on/off
    GET    /flags/{key}/audit  - Get audit history
"""

import math
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import FlagServiceDep, Tenant
from app.core.exceptions import NotFoundError
from app.schemas.flag import (
    FlagAuditLogResponse,
    FlagCreate,
    FlagListResponse,
    FlagResponse,
    FlagUpdate,
)
from app.services.flag_service import FlagService

router = APIRouter(prefix="/flags", tags=["flags"])


@router.post(
    "",
    response_model=FlagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new feature flag",
    description="""
    Create a new feature flag for the tenant.
    
    The flag key must be unique within the tenant and follow the pattern:
    lowercase alphanumeric with hyphens (e.g., 'dark-mode', 'new-checkout-v2').
    
    **Rollout Percentage:**
    - 0 = Flag always returns false
    - 100 = Flag always returns true (for enabled users)
    - 1-99 = Percentage of users who see the feature
    """,
)
async def create_flag(
    flag_in: FlagCreate,
    flag_service: FlagServiceDep,
    tenant: Tenant,
) -> FlagResponse:
    """
    Create a new feature flag.
    
    - **key**: Unique identifier (lowercase, hyphens allowed)
    - **name**: Human-readable display name
    - **rollout_percentage**: 0-100, percentage of users who see the feature
    - **is_enabled**: Master switch (default: true)
    """
    flag = await flag_service.create_flag(
        flag_in=flag_in,
        actor_id=tenant.user_id,
        actor_email=tenant.user_email,
    )
    return FlagResponse.model_validate(flag)


@router.get(
    "",
    response_model=FlagListResponse,
    summary="List all feature flags",
    description="Get a paginated list of all feature flags for the tenant.",
)
async def list_flags(
    flag_service: FlagServiceDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            description="Filter by status: active, inactive, archived",
        ),
    ] = None,
) -> FlagListResponse:
    """
    List all feature flags with pagination.
    
    Use the `status` query parameter to filter by flag status.
    """
    flags, total = await flag_service.list_flags(
        page=page,
        page_size=page_size,
        status=status_filter,
    )
    
    return FlagListResponse(
        items=[FlagResponse.model_validate(f) for f in flags],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get(
    "/{flag_key}",
    response_model=FlagResponse,
    summary="Get a feature flag",
    description="Get a feature flag by its unique key.",
)
async def get_flag(
    flag_key: str,
    flag_service: FlagServiceDep,
) -> FlagResponse:
    """
    Get a feature flag by key.
    
    - **flag_key**: The unique key of the flag (e.g., 'dark-mode')
    """
    flag = await flag_service.get_flag(flag_key)
    return FlagResponse.model_validate(flag)


@router.patch(
    "/{flag_key}",
    response_model=FlagResponse,
    summary="Update a feature flag",
    description="""
    Update a feature flag's properties.
    
    Only provided fields will be updated. The key cannot be changed.
    """,
)
async def update_flag(
    flag_key: str,
    flag_in: FlagUpdate,
    flag_service: FlagServiceDep,
    tenant: Tenant,
) -> FlagResponse:
    """
    Update a feature flag.
    
    Partial updates are supported - only include fields you want to change.
    """
    flag = await flag_service.update_flag(
        flag_key=flag_key,
        flag_in=flag_in,
        actor_id=tenant.user_id,
        actor_email=tenant.user_email,
    )
    return FlagResponse.model_validate(flag)


@router.delete(
    "/{flag_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a feature flag",
    description="Permanently delete a feature flag. This action cannot be undone.",
)
async def delete_flag(
    flag_key: str,
    flag_service: FlagServiceDep,
    tenant: Tenant,
) -> None:
    """
    Delete a feature flag.
    
    **Warning:** This permanently deletes the flag and all its audit history.
    Consider archiving (status=archived) instead for production flags.
    """
    await flag_service.delete_flag(
        flag_key=flag_key,
        actor_id=tenant.user_id,
        actor_email=tenant.user_email,
    )


@router.post(
    "/{flag_key}/toggle",
    response_model=FlagResponse,
    summary="Toggle a feature flag",
    description="Quickly enable or disable a feature flag.",
)
async def toggle_flag(
    flag_key: str,
    is_enabled: bool,
    flag_service: FlagServiceDep,
    tenant: Tenant,
) -> FlagResponse:
    """
    Toggle a flag on or off.
    
    - **is_enabled=true**: Enable the flag
    - **is_enabled=false**: Disable the flag (always returns false)
    """
    flag = await flag_service.toggle_flag(
        flag_key=flag_key,
        is_enabled=is_enabled,
        actor_id=tenant.user_id,
        actor_email=tenant.user_email,
    )
    return FlagResponse.model_validate(flag)


@router.get(
    "/{flag_key}/audit",
    response_model=list[FlagAuditLogResponse],
    summary="Get flag audit history",
    description="Get the change history for a feature flag.",
)
async def get_flag_audit_log(
    flag_key: str,
    flag_service: FlagServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[FlagAuditLogResponse]:
    """
    Get audit logs for a flag.
    
    Returns the most recent changes, newest first.
    """
    # First get the flag to get its ID
    flag = await flag_service.get_flag(flag_key)
    
    # Import crud_flag to get audit logs
    from app.crud.crud_flag import crud_flag
    
    logs = await crud_flag.get_audit_logs(
        flag_service.db,
        flag_service.tenant_id,
        flag.id,
        limit=limit,
    )
    
    return [FlagAuditLogResponse.model_validate(log) for log in logs]
