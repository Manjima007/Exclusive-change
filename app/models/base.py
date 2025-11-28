"""
SQLAlchemy Base Model.

This module defines the declarative base class and common mixins
used by all database models in the application.

Design Principles:
    - All models inherit from Base for table creation
    - TimestampMixin provides consistent created_at/updated_at
    - UUIDs used for all primary keys (better for distributed systems)
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Naming convention for constraints (required for Alembic autogenerate)
# This ensures consistent, predictable constraint names across migrations
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """
    Declarative base class for all SQLAlchemy models.
    
    All models should inherit from this class to be recognized
    by Alembic for migrations and by SQLAlchemy for queries.
    
    Attributes:
        metadata: SQLAlchemy metadata with naming convention.
        type_annotation_map: Maps Python types to SQL types.
    
    Example:
        class User(Base):
            __tablename__ = "users"
            
            id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
            name: Mapped[str] = mapped_column(String(100))
    """
    
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    
    # Type annotation map for common types
    type_annotation_map: dict[type, Any] = {
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }
    
    def __repr__(self) -> str:
        """Generate a readable string representation."""
        class_name = self.__class__.__name__
        # Get primary key columns
        pk_cols = [col.name for col in self.__table__.primary_key.columns]
        pk_values = [getattr(self, col, None) for col in pk_cols]
        pk_str = ", ".join(f"{k}={v}" for k, v in zip(pk_cols, pk_values))
        return f"<{class_name}({pk_str})>"


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at columns.
    
    Use this mixin for any model that needs to track when records
    were created and last modified.
    
    Attributes:
        created_at: Timestamp when record was created (auto-set).
        updated_at: Timestamp when record was last updated (auto-set).
    
    Example:
        class Flag(TimestampMixin, Base):
            __tablename__ = "flags"
            # ... other columns
    
    Note:
        updated_at is automatically set on UPDATE via onupdate=func.now()
    """
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
