"""
Feature Flag SQLAlchemy Models.

This module defines the core feature flag data structures:
    - Flag: A feature toggle with percentage rollout
    - FlagAuditLog: Immutable log of all flag changes

Flag Evaluation Logic:
    Flags use percentage rollout with deterministic hashing:
    - MD5(user_id + flag_key) % 100 produces a number 0-99
    - If the number < rollout_percentage, the flag is ON for that user
    - This ensures user "stickiness" - same user always gets same result

Database Schema:
    flags
    ├── id (PK, UUID)
    ├── tenant_id (FK → tenants)
    ├── key (unique within tenant)
    ├── name
    ├── description
    ├── rollout_percentage (0-100)
    ├── is_enabled
    └── timestamps
    
    flag_audit_logs
    ├── id (PK, UUID)
    ├── flag_id (FK → flags)
    ├── tenant_id (FK → tenants)
    ├── action (created, updated, deleted)
    ├── changes (JSONB)
    ├── actor_id (who made the change)
    └── created_at
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class FlagStatus(str, Enum):
    """Possible states of a feature flag."""
    
    ACTIVE = "active"       # Flag is enabled and can be evaluated
    INACTIVE = "inactive"   # Flag is disabled (always returns False)
    ARCHIVED = "archived"   # Flag is soft-deleted


class AuditAction(str, Enum):
    """Types of auditable actions on flags."""
    
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ROLLOUT_CHANGED = "rollout_changed"


class Flag(TimestampMixin, Base):
    """
    Represents a feature flag with percentage-based rollout.
    
    Feature flags allow gradual rollout of features to a percentage
    of users. The evaluation uses deterministic hashing to ensure
    consistent results for the same user.
    
    Attributes:
        id: Unique identifier (UUID).
        tenant_id: Parent tenant reference (REQUIRED for multi-tenancy).
        key: Machine-readable identifier (e.g., "dark-mode").
        name: Human-readable name (e.g., "Dark Mode").
        description: Detailed description of the flag's purpose.
        rollout_percentage: Percentage of users who see the feature (0-100).
        is_enabled: Master switch - if False, flag always evaluates to False.
        status: Current state (active, inactive, archived).
        
    Evaluation Logic:
        1. If is_enabled is False → return False
        2. If status is not ACTIVE → return False
        3. Compute: hash = MD5(user_id + key) % 100
        4. Return: hash < rollout_percentage
    
    Example:
        flag = Flag(
            tenant_id=tenant.id,
            key="new-checkout-flow",
            name="New Checkout Flow",
            description="Redesigned checkout experience",
            rollout_percentage=25,  # 25% of users
            is_enabled=True,
        )
    """
    
    __tablename__ = "flags"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Foreign Key - Tenant (CRITICAL for multi-tenancy)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant that owns this flag (multi-tenancy key)",
    )
    
    # Flag Identification
    key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Machine-readable key (e.g., 'dark-mode')",
    )
    
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable name",
    )
    
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed description of what this flag controls",
    )
    
    # Rollout Configuration
    rollout_percentage: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Percentage of users who see the feature (0-100)",
    )
    
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Master switch - if False, flag always evaluates to False",
    )
    
    status: Mapped[str] = mapped_column(
        String(20),
        default=FlagStatus.ACTIVE.value,
        nullable=False,
        comment="Current state: active, inactive, archived",
    )
    
    # Metadata
    tags: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Optional tags for organization (e.g., {'team': 'payments'})",
    )
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="flags",
    )
    
    audit_logs: Mapped[list["FlagAuditLog"]] = relationship(
        "FlagAuditLog",
        back_populates="flag",
        cascade="all, delete-orphan",
        order_by="desc(FlagAuditLog.created_at)",
    )
    
    # Indexes and Constraints
    __table_args__ = (
        # Unique constraint: flag key must be unique within a tenant
        Index(
            "ix_flags_tenant_key",
            "tenant_id",
            "key",
            unique=True,
        ),
        # Check constraint: rollout_percentage must be 0-100
        CheckConstraint(
            "rollout_percentage >= 0 AND rollout_percentage <= 100",
            name="ck_flags_rollout_percentage_range",
        ),
        # Index for common query patterns
        Index(
            "ix_flags_tenant_status",
            "tenant_id",
            "status",
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Flag(id={self.id}, key='{self.key}', rollout={self.rollout_percentage}%)>"


class FlagAuditLog(Base):
    """
    Immutable audit log for all flag changes.
    
    Every modification to a flag creates a new audit log entry.
    This provides:
        - Compliance: Who changed what, and when
        - Debugging: Track down when issues were introduced
        - Rollback: Reference for reverting changes
    
    Attributes:
        id: Unique identifier (UUID).
        flag_id: The flag that was changed.
        tenant_id: Tenant for multi-tenancy filtering.
        action: Type of change (created, updated, deleted, etc.).
        changes: JSONB containing before/after values.
        actor_id: UUID of the user who made the change.
        actor_email: Email of the user (denormalized for display).
        created_at: When the change occurred.
    
    Example changes JSONB:
        {
            "before": {"rollout_percentage": 10},
            "after": {"rollout_percentage": 50}
        }
    """
    
    __tablename__ = "flag_audit_logs"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Foreign Keys
    flag_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("flags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Denormalized for efficient multi-tenant queries",
    )
    
    # Audit Information
    action: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Type of action: created, updated, deleted, etc.",
    )
    
    changes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Before/after values for the change",
    )
    
    # Actor Information
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        comment="UUID of the user who made the change",
    )
    
    actor_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Email of the actor (denormalized for display)",
    )
    
    # Timestamp (immutable - no updated_at needed)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    # Relationships
    flag: Mapped["Flag"] = relationship(
        "Flag",
        back_populates="audit_logs",
    )
    
    # Indexes
    __table_args__ = (
        # Index for fetching audit history
        Index(
            "ix_flag_audit_logs_flag_created",
            "flag_id",
            "created_at",
        ),
        # Index for tenant-wide audit queries
        Index(
            "ix_flag_audit_logs_tenant_created",
            "tenant_id",
            "created_at",
        ),
    )
    
    def __repr__(self) -> str:
        return f"<FlagAuditLog(id={self.id}, action='{self.action}')>"
