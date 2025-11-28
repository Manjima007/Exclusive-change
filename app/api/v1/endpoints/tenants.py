"""
Tenant Management Endpoints.

These endpoints manage tenants (organizations using the service).
Note: In production, tenant creation might be restricted to admin users.

Endpoints:
    POST   /tenants           - Create a new tenant
    GET    /tenants           - List all tenants (admin only)
    GET    /tenants/{id}      - Get a tenant by ID
    PATCH  /tenants/{id}      - Update a tenant
    DELETE /tenants/{id}      - Delete a tenant
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DatabaseSession
from app.crud.crud_tenant import crud_tenant
from app.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantUpdate,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tenant",
    description="""
    Create a new tenant (organization) in the system.
    
    This will automatically create default environments:
    - Development
    - Staging  
    - Production (default)
    """,
)
async def create_tenant(
    tenant_in: TenantCreate,
    db: DatabaseSession,
    user: CurrentUser,
) -> TenantResponse:
    """
    Create a new tenant.
    
    - **name**: Company/organization name
    - **slug**: URL-safe identifier (must be unique)
    """
    # Check if slug already exists
    existing = await crud_tenant.get_by_slug(db, tenant_in.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with slug '{tenant_in.slug}' already exists",
        )
    
    tenant = await crud_tenant.create(db, obj_in=tenant_in)
    await db.commit()
    return TenantResponse.model_validate(tenant)


@router.get(
    "",
    response_model=list[TenantResponse],
    summary="List all tenants",
    description="Get a list of all tenants. Admin access recommended.",
)
async def list_tenants(
    db: DatabaseSession,
    user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> list[TenantResponse]:
    """List all tenants with pagination."""
    tenants = await crud_tenant.get_multi(db, skip=skip, limit=limit)
    return [TenantResponse.model_validate(t) for t in tenants]


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Get a tenant",
    description="Get a tenant by its ID.",
)
async def get_tenant(
    tenant_id: uuid.UUID,
    db: DatabaseSession,
    user: CurrentUser,
) -> TenantResponse:
    """Get a tenant by ID."""
    tenant = await crud_tenant.get(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantResponse.model_validate(tenant)


@router.get(
    "/slug/{slug}",
    response_model=TenantResponse,
    summary="Get a tenant by slug",
    description="Get a tenant by its URL-safe slug.",
)
async def get_tenant_by_slug(
    slug: str,
    db: DatabaseSession,
    user: CurrentUser,
) -> TenantResponse:
    """Get a tenant by slug."""
    tenant = await crud_tenant.get_by_slug(db, slug)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with slug '{slug}' not found",
        )
    return TenantResponse.model_validate(tenant)


@router.patch(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Update a tenant",
    description="Update a tenant's properties.",
)
async def update_tenant(
    tenant_id: uuid.UUID,
    tenant_in: TenantUpdate,
    db: DatabaseSession,
    user: CurrentUser,
) -> TenantResponse:
    """Update a tenant."""
    tenant = await crud_tenant.get(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    updated_tenant = await crud_tenant.update(db, db_obj=tenant, obj_in=tenant_in)
    await db.commit()
    return TenantResponse.model_validate(updated_tenant)


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tenant",
    description="Delete a tenant and all associated data (environments, flags, API keys).",
)
async def delete_tenant(
    tenant_id: uuid.UUID,
    db: DatabaseSession,
    user: CurrentUser,
) -> None:
    """Delete a tenant."""
    tenant = await crud_tenant.get(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    await crud_tenant.delete(db, id=tenant_id)
    await db.commit()
