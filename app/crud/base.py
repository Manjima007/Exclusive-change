"""
Base CRUD Class.

This module provides a generic CRUD (Create, Read, Update, Delete) base class
that can be extended for specific models. It enforces multi-tenancy filtering.

Design Principles:
    - All queries MUST filter by tenant_id (multi-tenancy)
    - All operations are async for non-blocking I/O
    - Generic type parameters for type safety
"""

import uuid
from typing import Any, Generic, Sequence, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

# Type variables for generic CRUD
ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Generic CRUD base class with common database operations.
    
    All queries filter by tenant_id to ensure multi-tenancy isolation.
    
    Type Parameters:
        ModelType: The SQLAlchemy model class.
        CreateSchemaType: Pydantic schema for create operations.
        UpdateSchemaType: Pydantic schema for update operations.
    
    Example:
        class CRUDFlag(CRUDBase[Flag, FlagCreate, FlagUpdate]):
            async def get_by_key(
                self, db: AsyncSession, tenant_id: UUID, key: str
            ) -> Flag | None:
                # Custom method
                ...
        
        crud_flag = CRUDFlag(Flag)
    """
    
    def __init__(self, model: Type[ModelType]) -> None:
        """
        Initialize CRUD with the model class.
        
        Args:
            model: SQLAlchemy model class to perform operations on.
        """
        self.model = model
    
    async def get(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        id: uuid.UUID,
    ) -> ModelType | None:
        """
        Get a single record by ID, filtered by tenant.
        
        Args:
            db: Database session.
            tenant_id: Tenant ID for multi-tenancy filtering.
            id: Record ID.
        
        Returns:
            The record if found, None otherwise.
        """
        query = select(self.model).where(
            self.model.tenant_id == tenant_id,  # type: ignore
            self.model.id == id,  # type: ignore
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_multi(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelType]:
        """
        Get multiple records with pagination, filtered by tenant.
        
        Args:
            db: Database session.
            tenant_id: Tenant ID for multi-tenancy filtering.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.
        
        Returns:
            List of records.
        """
        query = (
            select(self.model)
            .where(self.model.tenant_id == tenant_id)  # type: ignore
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return result.scalars().all()
    
    async def count(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> int:
        """
        Count total records for a tenant.
        
        Args:
            db: Database session.
            tenant_id: Tenant ID for multi-tenancy filtering.
        
        Returns:
            Total count of records.
        """
        query = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.tenant_id == tenant_id)  # type: ignore
        )
        result = await db.execute(query)
        return result.scalar() or 0
    
    async def create(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        obj_in: CreateSchemaType,
    ) -> ModelType:
        """
        Create a new record.
        
        Args:
            db: Database session.
            tenant_id: Tenant ID to associate with the record.
            obj_in: Pydantic schema with creation data.
        
        Returns:
            The created record.
        """
        obj_data = obj_in.model_dump()
        obj_data["tenant_id"] = tenant_id
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj
    
    async def update(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any],
    ) -> ModelType:
        """
        Update an existing record.
        
        Args:
            db: Database session.
            tenant_id: Tenant ID for verification.
            db_obj: Existing database object to update.
            obj_in: Pydantic schema or dict with update data.
        
        Returns:
            The updated record.
        
        Raises:
            ValueError: If tenant_id doesn't match the record.
        """
        # Security check: ensure we're updating our own tenant's data
        if getattr(db_obj, "tenant_id", None) != tenant_id:
            raise ValueError("Cannot update record from different tenant")
        
        # Convert Pydantic model to dict if needed
        if isinstance(obj_in, BaseModel):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = obj_in
        
        # Update fields
        for field, value in update_data.items():
            if hasattr(db_obj, field):
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
        """
        Delete a record by ID.
        
        Args:
            db: Database session.
            tenant_id: Tenant ID for multi-tenancy filtering.
            id: Record ID to delete.
        
        Returns:
            True if deleted, False if not found.
        """
        obj = await self.get(db, tenant_id, id)
        if obj:
            await db.delete(obj)
            await db.flush()
            return True
        return False
    
    def _apply_filters(
        self,
        query: Select,
        tenant_id: uuid.UUID,
        **filters: Any,
    ) -> Select:
        """
        Apply common filters to a query.
        
        Args:
            query: SQLAlchemy select query.
            tenant_id: Tenant ID for multi-tenancy filtering.
            **filters: Additional field=value filters.
        
        Returns:
            Query with filters applied.
        """
        query = query.where(self.model.tenant_id == tenant_id)  # type: ignore
        
        for field, value in filters.items():
            if value is not None and hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)
        
        return query
