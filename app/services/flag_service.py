"""
Flag Management Service.

This module provides business logic for flag CRUD operations.
It orchestrates between CRUD, caching, and validation layers.
"""

import logging
import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import RedisCache
from app.core.exceptions import ConflictError, NotFoundError
from app.crud.crud_flag import crud_flag
from app.models.flag import Flag
from app.schemas.flag import FlagCreate, FlagResponse, FlagUpdate

logger = logging.getLogger(__name__)


class FlagService:
    """
    Service layer for feature flag management.
    
    Handles business logic including:
        - Validation (unique key, valid percentage)
        - Cache invalidation on updates
        - Audit logging coordination
    """
    
    def __init__(
        self,
        db: AsyncSession,
        cache: RedisCache,
        tenant_id: uuid.UUID,
    ) -> None:
        """
        Initialize the flag service.
        
        Args:
            db: Database session.
            cache: Redis cache instance.
            tenant_id: Tenant context.
        """
        self.db = db
        self.cache = cache
        self.tenant_id = tenant_id
    
    async def create_flag(
        self,
        flag_in: FlagCreate,
        actor_id: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> Flag:
        """
        Create a new feature flag.
        
        Args:
            flag_in: Flag creation data.
            actor_id: ID of the user creating the flag.
            actor_email: Email of the creating user.
        
        Returns:
            The created flag.
        
        Raises:
            ConflictError: If a flag with the same key already exists.
        """
        # Check for existing flag with same key
        existing = await crud_flag.get_by_key(
            self.db, self.tenant_id, flag_in.key
        )
        if existing:
            raise ConflictError(
                resource="Flag",
                message=f"Flag with key '{flag_in.key}' already exists",
                details={"key": flag_in.key},
            )
        
        # Create the flag with audit log
        flag = await crud_flag.create_with_audit(
            self.db,
            self.tenant_id,
            obj_in=flag_in,
            actor_id=actor_id,
            actor_email=actor_email,
        )
        
        # Invalidate cache
        await self.cache.invalidate_flags(self.tenant_id)
        
        logger.info(f"Created flag '{flag.key}' for tenant {self.tenant_id}")
        return flag
    
    async def get_flag(self, flag_key: str) -> Flag:
        """
        Get a flag by key.
        
        Args:
            flag_key: The flag's unique key.
        
        Returns:
            The flag.
        
        Raises:
            NotFoundError: If flag not found.
        """
        flag = await crud_flag.get_by_key(self.db, self.tenant_id, flag_key)
        if not flag:
            raise NotFoundError(resource="Flag", identifier=flag_key)
        return flag
    
    async def get_flag_by_id(self, flag_id: uuid.UUID) -> Flag:
        """
        Get a flag by ID.
        
        Args:
            flag_id: The flag's UUID.
        
        Returns:
            The flag.
        
        Raises:
            NotFoundError: If flag not found.
        """
        flag = await crud_flag.get(self.db, self.tenant_id, flag_id)
        if not flag:
            raise NotFoundError(resource="Flag", identifier=str(flag_id))
        return flag
    
    async def list_flags(
        self,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
    ) -> tuple[Sequence[Flag], int]:
        """
        List flags with pagination.
        
        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            status: Optional status filter.
        
        Returns:
            Tuple of (flags, total_count).
        """
        return await crud_flag.get_multi_with_pagination(
            self.db,
            self.tenant_id,
            page=page,
            page_size=page_size,
            status=status,
        )
    
    async def update_flag(
        self,
        flag_key: str,
        flag_in: FlagUpdate,
        actor_id: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> Flag:
        """
        Update a feature flag.
        
        Args:
            flag_key: The flag's key.
            flag_in: Update data.
            actor_id: ID of the user making the update.
            actor_email: Email of the updating user.
        
        Returns:
            The updated flag.
        
        Raises:
            NotFoundError: If flag not found.
        """
        # Get existing flag
        flag = await self.get_flag(flag_key)
        
        # Update with audit log
        updated_flag = await crud_flag.update_with_audit(
            self.db,
            self.tenant_id,
            db_obj=flag,
            obj_in=flag_in,
            actor_id=actor_id,
            actor_email=actor_email,
        )
        
        # Invalidate cache
        await self.cache.invalidate_flag(self.tenant_id, flag_key)
        await self.cache.invalidate_flags(self.tenant_id)
        
        logger.info(f"Updated flag '{flag_key}' for tenant {self.tenant_id}")
        return updated_flag
    
    async def delete_flag(
        self,
        flag_key: str,
        actor_id: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> bool:
        """
        Delete a feature flag.
        
        Args:
            flag_key: The flag's key.
            actor_id: ID of the user deleting.
            actor_email: Email of the deleting user.
        
        Returns:
            True if deleted.
        
        Raises:
            NotFoundError: If flag not found.
        """
        # Get existing flag
        flag = await self.get_flag(flag_key)
        
        # Delete with audit
        result = await crud_flag.delete_with_audit(
            self.db,
            self.tenant_id,
            db_obj=flag,
            actor_id=actor_id,
            actor_email=actor_email,
        )
        
        # Invalidate cache
        await self.cache.invalidate_flag(self.tenant_id, flag_key)
        await self.cache.invalidate_flags(self.tenant_id)
        
        logger.info(f"Deleted flag '{flag_key}' for tenant {self.tenant_id}")
        return result
    
    async def toggle_flag(
        self,
        flag_key: str,
        is_enabled: bool,
        actor_id: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> Flag:
        """
        Toggle a flag on or off.
        
        Convenience method for quickly enabling/disabling a flag.
        
        Args:
            flag_key: The flag's key.
            is_enabled: New enabled state.
            actor_id: ID of the user toggling.
            actor_email: Email of the toggling user.
        
        Returns:
            The updated flag.
        """
        update = FlagUpdate(is_enabled=is_enabled)
        return await self.update_flag(
            flag_key, update, actor_id, actor_email
        )
    
    async def set_rollout_percentage(
        self,
        flag_key: str,
        percentage: int,
        actor_id: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> Flag:
        """
        Update a flag's rollout percentage.
        
        Convenience method for adjusting rollout.
        
        Args:
            flag_key: The flag's key.
            percentage: New percentage (0-100).
            actor_id: ID of the user updating.
            actor_email: Email of the updating user.
        
        Returns:
            The updated flag.
        """
        update = FlagUpdate(rollout_percentage=percentage)
        return await self.update_flag(
            flag_key, update, actor_id, actor_email
        )


async def get_flag_service(
    db: AsyncSession,
    cache: RedisCache,
    tenant_id: uuid.UUID,
) -> FlagService:
    """Factory function for dependency injection."""
    return FlagService(db, cache, tenant_id)
