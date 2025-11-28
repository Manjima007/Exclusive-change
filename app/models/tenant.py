"""
Tenant-related SQLAlchemy Models.

This module defines the multi-tenancy data structures:
    - Tenant: A company/organization using the service
    - Environment: Isolated spaces within a tenant (dev, staging, prod)
    - APIKey: Authentication keys for SDK/evaluation API access

Multi-Tenancy Design:
    Every query in the application MUST filter by tenant_id to prevent
    data leakage between tenants. This is enforced at the CRUD layer.

Database Schema:
    tenants
    ├── id (PK, UUID)
    ├── name (unique)
    ├── slug (unique, URL-safe)
    └── timestamps
    
    environments
    ├── id (PK, UUID)
    ├── tenant_id (FK → tenants)
    ├── name
    ├── key (unique within tenant)
    └── timestamps
    
    api_keys
    ├── id (PK, UUID)
    ├── tenant_id (FK → tenants)
    ├── environment_id (FK → environments)
    ├── key_hash (hashed key)
    ├── key_prefix (first 8 chars for lookup)
    └── timestamps
"""

import secrets
import uuid
from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.flag import Flag


class Tenant(TimestampMixin, Base):
    """
    Represents a company/organization using the feature flag service.
    
    Each tenant has isolated data - flags, environments, and API keys
    are scoped to a single tenant.
    
    Attributes:
        id: Unique identifier (UUID).
        name: Human-readable company name.
        slug: URL-safe identifier for API routes.
        is_active: Whether the tenant account is active.
        
    Relationships:
        environments: List of environments (dev, staging, prod).
        api_keys: List of API keys for SDK access.
        flags: List of feature flags.
    
    Example:
        tenant = Tenant(
            name="Acme Corporation",
            slug="acme-corp",
        )
    """
    
    __tablename__ = "tenants"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Tenant Information
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable company name",
    )
    
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-safe identifier (e.g., 'acme-corp')",
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the tenant account is active",
    )
    
    # Relationships
    environments: Mapped[list["Environment"]] = relationship(
        "Environment",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",  # Eager load by default
    )
    
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    
    flags: Mapped[list["Flag"]] = relationship(
        "Flag",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, slug='{self.slug}')>"


class Environment(TimestampMixin, Base):
    """
    Represents an isolated environment within a tenant.
    
    Environments allow tenants to have different flag configurations
    for development, staging, and production.
    
    Attributes:
        id: Unique identifier (UUID).
        tenant_id: Parent tenant reference.
        name: Human-readable name (e.g., "Production").
        key: Machine-readable key (e.g., "production").
        description: Optional description.
        is_default: Whether this is the default environment.
        color: UI color for visual distinction.
    
    Example:
        env = Environment(
            tenant_id=tenant.id,
            name="Production",
            key="production",
            is_default=False,
        )
    """
    
    __tablename__ = "environments"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Foreign Key - Tenant
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Environment Information
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable name (e.g., 'Production')",
    )
    
    key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Machine-readable key (e.g., 'production')",
    )
    
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description of the environment",
    )
    
    # Status
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether this is the default environment for the tenant",
    )
    
    # UI Customization
    color: Mapped[str] = mapped_column(
        String(7),
        default="#6B7280",
        nullable=False,
        comment="Hex color for UI display",
    )
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="environments",
    )
    
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="environment",
        cascade="all, delete-orphan",
    )
    
    # Indexes
    __table_args__ = (
        # Unique constraint: environment key must be unique within a tenant
        Index(
            "ix_environments_tenant_key",
            "tenant_id",
            "key",
            unique=True,
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Environment(id={self.id}, key='{self.key}')>"


class APIKey(TimestampMixin, Base):
    """
    API Key for SDK/client authentication on the Evaluation API.
    
    Security Design:
        - Only the hash of the key is stored (SHA-256)
        - key_prefix stores first 8 chars for identification
        - Full key is shown only once at creation time
    
    Attributes:
        id: Unique identifier (UUID).
        tenant_id: Parent tenant reference.
        environment_id: Associated environment.
        name: Human-readable name for the key.
        key_hash: SHA-256 hash of the full key.
        key_prefix: First 8 characters for display/lookup.
        is_active: Whether the key is currently valid.
        last_used_at: Timestamp of last successful use.
    
    Example:
        # Creating a new API key
        raw_key = APIKey.generate_key()  # Returns full key
        api_key = APIKey(
            tenant_id=tenant.id,
            environment_id=env.id,
            name="Production SDK Key",
            key_hash=APIKey.hash_key(raw_key),
            key_prefix=raw_key[:8],
        )
        # Return raw_key to user (only time it's visible)
    """
    
    __tablename__ = "api_keys"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Foreign Keys
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    environment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Key Information
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable name for identification",
    )
    
    key_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 produces 64 hex characters
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the full API key",
    )
    
    key_prefix: Mapped[str] = mapped_column(
        String(12),  # "xc_live_" + first 4 chars
        nullable=False,
        index=True,
        comment="Prefix for key identification (e.g., 'xc_live_a1b2')",
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the API key is currently valid",
    )
    
    # Usage Tracking
    last_used_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Timestamp of last successful authentication",
    )
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="api_keys",
    )
    
    environment: Mapped["Environment"] = relationship(
        "Environment",
        back_populates="api_keys",
    )
    
    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, prefix='{self.key_prefix}')>"
    
    @staticmethod
    def generate_key(prefix: str = "xc_live_") -> str:
        """
        Generate a new random API key.
        
        Format: {prefix}{32 random hex characters}
        Example: xc_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
        
        Args:
            prefix: Prefix to prepend to the key.
        
        Returns:
            str: The full API key (show only once to user).
        """
        random_part = secrets.token_hex(16)  # 32 characters
        return f"{prefix}{random_part}"
    
    @staticmethod
    def hash_key(raw_key: str) -> str:
        """
        Hash an API key using SHA-256.
        
        Args:
            raw_key: The raw API key to hash.
        
        Returns:
            str: SHA-256 hash as hexadecimal string.
        """
        return sha256(raw_key.encode()).hexdigest()
    
    @staticmethod
    def get_prefix(raw_key: str, length: int = 12) -> str:
        """
        Extract the display prefix from a raw API key.
        
        Args:
            raw_key: The full API key.
            length: Number of characters to include.
        
        Returns:
            str: The prefix for display/lookup.
        """
        return raw_key[:length]
