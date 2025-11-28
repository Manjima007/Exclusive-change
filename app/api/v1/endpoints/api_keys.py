"""
API Key Management Endpoints.

These endpoints manage API keys for SDK/client authentication.
API keys are scoped to a specific tenant and environment.

Security:
    - Full key is only shown ONCE at creation time
    - Only the hash is stored in the database
    - Keys can be revoked (deleted) at any time

Endpoints:
    POST   /api-keys           - Create a new API key
    GET    /api-keys           - List all API keys for tenant
    GET    /api-keys/{id}      - Get an API key by ID
    PATCH  /api-keys/{id}      - Update an API key (name, active status)
    DELETE /api-keys/{id}      - Revoke (delete) an API key
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DatabaseSession, Tenant
from app.crud.crud_tenant import crud_api_key, crud_environment
from app.models.tenant import APIKey
from app.schemas.tenant import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyUpdate,
)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description="""
    Create a new API key for SDK authentication.
    
    **⚠️ IMPORTANT:** The full API key is only shown in this response.
    Save it securely - it cannot be retrieved again!
    
    The key is tied to a specific environment (dev/staging/production).
    """,
)
async def create_api_key(
    api_key_in: APIKeyCreate,
    db: DatabaseSession,
    tenant: Tenant,
) -> APIKeyCreateResponse:
    """
    Create a new API key.
    
    - **name**: Human-readable name (e.g., "Production SDK Key")
    - **environment_id**: UUID of the environment this key accesses
    
    Returns the full API key - SAVE IT NOW!
    """
    # Verify environment exists and belongs to tenant
    environment = await crud_environment.get(
        db, tenant.tenant_id, api_key_in.environment_id
    )
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )
    
    # Generate the raw API key
    raw_key = APIKey.generate_key()
    key_hash = APIKey.hash_key(raw_key)
    key_prefix = APIKey.get_prefix(raw_key)
    
    # Create the API key record
    api_key = await crud_api_key.create(
        db,
        tenant.tenant_id,
        obj_in=api_key_in,
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    await db.commit()
    await db.refresh(api_key)
    
    # Return response with the full key (only time it's visible)
    # Build the response manually to include the raw key
    return APIKeyCreateResponse(
        id=api_key.id,
        tenant_id=api_key.tenant_id,
        environment_id=api_key.environment_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        is_active=api_key.is_active,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
        key=raw_key,  # Include the full key
    )


@router.get(
    "",
    response_model=list[APIKeyResponse],
    summary="List all API keys",
    description="Get all API keys for the current tenant.",
)
async def list_api_keys(
    db: DatabaseSession,
    tenant: Tenant,
) -> list[APIKeyResponse]:
    """List all API keys for the tenant."""
    api_keys = await crud_api_key.get_multi(db, tenant.tenant_id)
    return [APIKeyResponse.model_validate(k) for k in api_keys]


@router.get(
    "/by-environment/{environment_id}",
    response_model=list[APIKeyResponse],
    summary="List API keys by environment",
    description="Get all API keys for a specific environment.",
)
async def list_api_keys_by_environment(
    environment_id: uuid.UUID,
    db: DatabaseSession,
    tenant: Tenant,
) -> list[APIKeyResponse]:
    """List API keys for a specific environment."""
    api_keys = await crud_api_key.get_by_environment(
        db, tenant.tenant_id, environment_id
    )
    return [APIKeyResponse.model_validate(k) for k in api_keys]


@router.get(
    "/{api_key_id}",
    response_model=APIKeyResponse,
    summary="Get an API key",
    description="Get an API key by its ID. The actual key value is not returned.",
)
async def get_api_key(
    api_key_id: uuid.UUID,
    db: DatabaseSession,
    tenant: Tenant,
) -> APIKeyResponse:
    """Get an API key by ID."""
    api_key = await crud_api_key.get(db, tenant.tenant_id, api_key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return APIKeyResponse.model_validate(api_key)


@router.patch(
    "/{api_key_id}",
    response_model=APIKeyResponse,
    summary="Update an API key",
    description="Update an API key's name or active status.",
)
async def update_api_key(
    api_key_id: uuid.UUID,
    api_key_in: APIKeyUpdate,
    db: DatabaseSession,
    tenant: Tenant,
) -> APIKeyResponse:
    """Update an API key."""
    api_key = await crud_api_key.get(db, tenant.tenant_id, api_key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    updated_key = await crud_api_key.update(
        db, tenant.tenant_id, db_obj=api_key, obj_in=api_key_in
    )
    await db.commit()
    return APIKeyResponse.model_validate(updated_key)


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    description="Permanently revoke (delete) an API key. This action cannot be undone.",
)
async def delete_api_key(
    api_key_id: uuid.UUID,
    db: DatabaseSession,
    tenant: Tenant,
) -> None:
    """Revoke an API key."""
    api_key = await crud_api_key.get(db, tenant.tenant_id, api_key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    await crud_api_key.delete(db, tenant.tenant_id, id=api_key_id)
    await db.commit()


@router.post(
    "/{api_key_id}/revoke",
    response_model=APIKeyResponse,
    summary="Soft-revoke an API key",
    description="Deactivate an API key without deleting it. Can be reactivated later.",
)
async def revoke_api_key(
    api_key_id: uuid.UUID,
    db: DatabaseSession,
    tenant: Tenant,
) -> APIKeyResponse:
    """Soft-revoke an API key (set is_active=False)."""
    api_key = await crud_api_key.get(db, tenant.tenant_id, api_key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    updated_key = await crud_api_key.update(
        db, tenant.tenant_id, db_obj=api_key, obj_in=APIKeyUpdate(is_active=False)
    )
    await db.commit()
    return APIKeyResponse.model_validate(updated_key)


@router.post(
    "/{api_key_id}/activate",
    response_model=APIKeyResponse,
    summary="Reactivate an API key",
    description="Reactivate a previously revoked API key.",
)
async def activate_api_key(
    api_key_id: uuid.UUID,
    db: DatabaseSession,
    tenant: Tenant,
) -> APIKeyResponse:
    """Reactivate an API key (set is_active=True)."""
    api_key = await crud_api_key.get(db, tenant.tenant_id, api_key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    updated_key = await crud_api_key.update(
        db, tenant.tenant_id, db_obj=api_key, obj_in=APIKeyUpdate(is_active=True)
    )
    await db.commit()
    return APIKeyResponse.model_validate(updated_key)
