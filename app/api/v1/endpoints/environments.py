"""
Environment Management Endpoints.

This module provides CRUD endpoints for managing environments within a tenant.
Each tenant can have multiple environments (e.g., development, staging, production).

Endpoints:
    POST   /environments           - Create a new environment
    GET    /environments           - List all environments
    GET    /environments/{key}     - Get an environment by key
    PATCH  /environments/{key}     - Update an environment
    DELETE /environments/{key}     - Delete an environment
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DatabaseSession, Tenant
from app.crud.crud_tenant import crud_environment
from app.schemas.tenant import (
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentUpdate,
)

router = APIRouter(prefix="/environments", tags=["environments"])


@router.post(
    "",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new environment",
    description="Create a new environment for the tenant.",
)
async def create_environment(
    environment_in: EnvironmentCreate,
    db: DatabaseSession,
    tenant: Tenant,
) -> EnvironmentResponse:
    """
    Create a new environment.
    
    - **name**: Human-readable name (e.g., "Production")
    - **key**: Machine-readable key (e.g., "production")
    - **is_default**: Whether this is the default environment
    """
    # Check for existing environment with same key
    existing = await crud_environment.get_by_key(
        db, tenant.tenant_id, environment_in.key
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Environment with key '{environment_in.key}' already exists",
        )
    
    env = await crud_environment.create(
        db, tenant.tenant_id, obj_in=environment_in
    )
    return EnvironmentResponse.model_validate(env)


@router.get(
    "",
    response_model=list[EnvironmentResponse],
    summary="List all environments",
    description="Get all environments for the tenant.",
)
async def list_environments(
    db: DatabaseSession,
    tenant: Tenant,
) -> list[EnvironmentResponse]:
    """List all environments for the tenant."""
    environments = await crud_environment.get_multi(db, tenant.tenant_id)
    return [EnvironmentResponse.model_validate(env) for env in environments]


@router.get(
    "/{env_key}",
    response_model=EnvironmentResponse,
    summary="Get an environment",
    description="Get an environment by its key.",
)
async def get_environment(
    env_key: str,
    db: DatabaseSession,
    tenant: Tenant,
) -> EnvironmentResponse:
    """Get an environment by key."""
    env = await crud_environment.get_by_key(db, tenant.tenant_id, env_key)
    if not env:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment '{env_key}' not found",
        )
    return EnvironmentResponse.model_validate(env)


@router.patch(
    "/{env_key}",
    response_model=EnvironmentResponse,
    summary="Update an environment",
    description="Update an environment's properties. The key cannot be changed.",
)
async def update_environment(
    env_key: str,
    environment_in: EnvironmentUpdate,
    db: DatabaseSession,
    tenant: Tenant,
) -> EnvironmentResponse:
    """Update an environment."""
    env = await crud_environment.get_by_key(db, tenant.tenant_id, env_key)
    if not env:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment '{env_key}' not found",
        )
    
    updated_env = await crud_environment.update(
        db, tenant.tenant_id, db_obj=env, obj_in=environment_in
    )
    return EnvironmentResponse.model_validate(updated_env)


@router.delete(
    "/{env_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an environment",
    description="Delete an environment. This will also delete all associated API keys.",
)
async def delete_environment(
    env_key: str,
    db: DatabaseSession,
    tenant: Tenant,
) -> None:
    """Delete an environment."""
    env = await crud_environment.get_by_key(db, tenant.tenant_id, env_key)
    if not env:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment '{env_key}' not found",
        )
    
    await crud_environment.delete(db, tenant.tenant_id, id=env.id)
