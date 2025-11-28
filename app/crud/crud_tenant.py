"""
Tenant, Environment, and API Key CRUD Operations.

This module provides data access operations for tenant-related entities.
Note: Tenant queries don't filter by tenant_id (they ARE the tenant).
"""

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tenant import APIKey, Environment, Tenant
from app.schemas.tenant import (
    APIKeyCreate,
    APIKeyUpdate,
    EnvironmentCreate,
    EnvironmentUpdate,
    TenantCreate,
    TenantUpdate,
)


# =============================================================================
# Tenant CRUD
# =============================================================================

class CRUDTenant:
    """
    CRUD operations for Tenants.
    
    Note: Tenant queries don't filter by tenant_id since tenants
    are the top-level entity in our multi-tenancy model.
    """
    
    async def get(
        self,
        db: AsyncSession,
        id: uuid.UUID,
    ) -> Tenant | None:
        """Get a tenant by ID."""
        query = (
            select(Tenant)
            .where(Tenant.id == id)
            .options(selectinload(Tenant.environments))
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Tenant | None:
        """Get a tenant by slug."""
        query = (
            select(Tenant)
            .where(Tenant.slug == slug)
            .options(selectinload(Tenant.environments))
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Tenant]:
        """Get multiple tenants with pagination."""
        query = (
            select(Tenant)
            .offset(skip)
            .limit(limit)
            .order_by(Tenant.created_at.desc())
        )
        result = await db.execute(query)
        return result.scalars().all()
    
    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: TenantCreate,
    ) -> Tenant:
        """Create a new tenant with default environments."""
        # Create tenant
        tenant = Tenant(**obj_in.model_dump())
        db.add(tenant)
        await db.flush()
        
        # Create default environments
        default_environments = [
            Environment(
                tenant_id=tenant.id,
                name="Development",
                key="development",
                color="#3B82F6",
                is_default=False,
            ),
            Environment(
                tenant_id=tenant.id,
                name="Staging",
                key="staging",
                color="#F59E0B",
                is_default=False,
            ),
            Environment(
                tenant_id=tenant.id,
                name="Production",
                key="production",
                color="#10B981",
                is_default=True,
            ),
        ]
        
        for env in default_environments:
            db.add(env)
        
        await db.flush()
        await db.refresh(tenant)
        return tenant
    
    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: Tenant,
        obj_in: TenantUpdate,
    ) -> Tenant:
        """Update a tenant."""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj
    
    async def delete(
        self,
        db: AsyncSession,
        *,
        id: uuid.UUID,
    ) -> bool:
        """Delete a tenant (cascades to all related data)."""
        tenant = await self.get(db, id)
        if tenant:
            await db.delete(tenant)
            await db.flush()
            return True
        return False


# =============================================================================
# Environment CRUD
# =============================================================================

class CRUDEnvironment:
    """CRUD operations for Environments."""
    
    async def get(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        id: uuid.UUID,
    ) -> Environment | None:
        """Get an environment by ID within a tenant."""
        query = select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.id == id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_key(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        key: str,
    ) -> Environment | None:
        """Get an environment by key within a tenant."""
        query = select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.key == key,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_default(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Environment | None:
        """Get the default environment for a tenant."""
        query = select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.is_default == True,  # noqa: E712
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_multi(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Sequence[Environment]:
        """Get all environments for a tenant."""
        query = (
            select(Environment)
            .where(Environment.tenant_id == tenant_id)
            .order_by(Environment.created_at)
        )
        result = await db.execute(query)
        return result.scalars().all()
    
    async def create(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        obj_in: EnvironmentCreate,
    ) -> Environment:
        """Create a new environment."""
        # If this is set as default, unset other defaults
        if obj_in.is_default:
            await self._unset_defaults(db, tenant_id)
        
        env = Environment(
            tenant_id=tenant_id,
            **obj_in.model_dump(),
        )
        db.add(env)
        await db.flush()
        await db.refresh(env)
        return env
    
    async def update(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        db_obj: Environment,
        obj_in: EnvironmentUpdate,
    ) -> Environment:
        """Update an environment."""
        update_data = obj_in.model_dump(exclude_unset=True)
        
        # Handle default flag change
        if update_data.get("is_default"):
            await self._unset_defaults(db, tenant_id)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj
    
    async def delete(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        id: uuid.UUID,
    ) -> bool:
        """Delete an environment."""
        env = await self.get(db, tenant_id, id)
        if env:
            await db.delete(env)
            await db.flush()
            return True
        return False
    
    async def _unset_defaults(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        """Unset is_default on all environments for a tenant."""
        from sqlalchemy import update
        stmt = (
            update(Environment)
            .where(Environment.tenant_id == tenant_id)
            .values(is_default=False)
        )
        await db.execute(stmt)


# =============================================================================
# API Key CRUD
# =============================================================================

class CRUDAPIKey:
    """CRUD operations for API Keys."""
    
    async def get(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        id: uuid.UUID,
    ) -> APIKey | None:
        """Get an API key by ID within a tenant."""
        query = select(APIKey).where(
            APIKey.tenant_id == tenant_id,
            APIKey.id == id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_hash(
        self,
        db: AsyncSession,
        key_hash: str,
    ) -> APIKey | None:
        """
        Get an API key by its hash.
        
        Used during authentication to validate API keys.
        Note: No tenant filter needed - hash is globally unique.
        """
        query = (
            select(APIKey)
            .where(
                APIKey.key_hash == key_hash,
                APIKey.is_active == True,  # noqa: E712
            )
            .options(
                selectinload(APIKey.tenant),
                selectinload(APIKey.environment),
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_multi(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Sequence[APIKey]:
        """Get all API keys for a tenant."""
        query = (
            select(APIKey)
            .where(APIKey.tenant_id == tenant_id)
            .order_by(APIKey.created_at.desc())
        )
        result = await db.execute(query)
        return result.scalars().all()
    
    async def get_by_environment(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        environment_id: uuid.UUID,
    ) -> Sequence[APIKey]:
        """Get all API keys for a specific environment."""
        query = (
            select(APIKey)
            .where(
                APIKey.tenant_id == tenant_id,
                APIKey.environment_id == environment_id,
            )
            .order_by(APIKey.created_at.desc())
        )
        result = await db.execute(query)
        return result.scalars().all()
    
    async def create(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        obj_in: APIKeyCreate,
        key_hash: str,
        key_prefix: str,
    ) -> APIKey:
        """
        Create a new API key.
        
        Args:
            db: Database session.
            tenant_id: Tenant ID.
            obj_in: API key creation data.
            key_hash: Pre-computed hash of the raw key.
            key_prefix: Prefix of the raw key for display.
        
        Returns:
            The created API key record.
        """
        api_key = APIKey(
            tenant_id=tenant_id,
            environment_id=obj_in.environment_id,
            name=obj_in.name,
            key_hash=key_hash,
            key_prefix=key_prefix,
        )
        db.add(api_key)
        await db.flush()
        await db.refresh(api_key)
        return api_key
    
    async def update(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        db_obj: APIKey,
        obj_in: APIKeyUpdate,
    ) -> APIKey:
        """Update an API key."""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj
    
    async def delete(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        id: uuid.UUID,
    ) -> bool:
        """Delete (revoke) an API key."""
        api_key = await self.get(db, tenant_id, id)
        if api_key:
            await db.delete(api_key)
            await db.flush()
            return True
        return False
    
    async def update_last_used(
        self,
        db: AsyncSession,
        api_key: APIKey,
    ) -> None:
        """Update the last_used_at timestamp."""
        from datetime import datetime, timezone
        api_key.last_used_at = datetime.now(timezone.utc)
        db.add(api_key)
        # Note: Don't flush here - let the request commit handle it


# Singleton instances for import convenience
crud_tenant = CRUDTenant()
crud_environment = CRUDEnvironment()
crud_api_key = CRUDAPIKey()
