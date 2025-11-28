"""
Pydantic Schemas for Tenant, Environment, and API Key.

This module defines the request/response schemas (DTOs) for tenant-related
operations. Schemas are separate from SQLAlchemy models to:
    1. Decouple API contract from database structure
    2. Control what data is exposed in responses
    3. Validate input with custom rules

Schema Naming Convention:
    - {Model}Create: Request body for creating a resource
    - {Model}Update: Request body for updating (all fields optional)
    - {Model}Response: Response body returned to clients
    - {Model}InDB: Internal representation with all fields
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# Tenant Schemas
# =============================================================================

class TenantBase(BaseModel):
    """Base schema with common tenant fields."""
    
    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Human-readable company name",
        examples=["Acme Corporation"],
    )
    
    slug: str = Field(
        ...,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe identifier (lowercase, hyphens allowed)",
        examples=["acme-corp"],
    )
    
    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Ensure slug is lowercase and URL-safe."""
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError(
                "Slug must be lowercase alphanumeric with hyphens "
                "(e.g., 'my-company')"
            )
        return v.lower()


class TenantCreate(TenantBase):
    """
    Request schema for creating a new tenant.
    
    Example:
        POST /api/v1/tenants
        {
            "name": "Acme Corporation",
            "slug": "acme-corp"
        }
    """
    pass


class TenantUpdate(BaseModel):
    """
    Request schema for updating a tenant.
    
    All fields are optional - only provided fields will be updated.
    
    Example:
        PATCH /api/v1/tenants/{id}
        {
            "name": "Acme Inc."
        }
    """
    
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )
    
    is_active: bool | None = Field(
        default=None,
        description="Whether the tenant account is active",
    )


class TenantResponse(TenantBase):
    """
    Response schema for tenant data.
    
    Includes all readable fields but excludes sensitive internal data.
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID = Field(description="Unique tenant identifier")
    is_active: bool = Field(description="Whether the tenant is active")
    created_at: datetime = Field(description="When the tenant was created")
    updated_at: datetime = Field(description="When the tenant was last updated")


# =============================================================================
# Environment Schemas
# =============================================================================

class EnvironmentBase(BaseModel):
    """Base schema with common environment fields."""
    
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Human-readable environment name",
        examples=["Production", "Staging", "Development"],
    )
    
    key: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="Machine-readable key",
        examples=["production", "staging", "development"],
    )
    
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Optional description",
    )
    
    color: str = Field(
        default="#6B7280",
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex color for UI display",
        examples=["#10B981", "#F59E0B", "#3B82F6"],
    )


class EnvironmentCreate(EnvironmentBase):
    """
    Request schema for creating a new environment.
    
    Example:
        POST /api/v1/environments
        {
            "name": "Production",
            "key": "production",
            "color": "#10B981"
        }
    """
    
    is_default: bool = Field(
        default=False,
        description="Whether this is the default environment",
    )


class EnvironmentUpdate(BaseModel):
    """
    Request schema for updating an environment.
    
    Key cannot be changed after creation.
    """
    
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_default: bool | None = Field(default=None)


class EnvironmentResponse(EnvironmentBase):
    """Response schema for environment data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID = Field(description="Unique environment identifier")
    tenant_id: uuid.UUID = Field(description="Parent tenant ID")
    is_default: bool = Field(description="Whether this is the default environment")
    created_at: datetime
    updated_at: datetime


# =============================================================================
# API Key Schemas
# =============================================================================

class APIKeyCreate(BaseModel):
    """
    Request schema for creating a new API key.
    
    Example:
        POST /api/v1/api-keys
        {
            "name": "Production SDK Key",
            "environment_id": "550e8400-e29b-41d4-a716-446655440000"
        }
    """
    
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Human-readable name for the key",
        examples=["Production SDK Key", "Mobile App Key"],
    )
    
    environment_id: uuid.UUID = Field(
        ...,
        description="ID of the environment this key accesses",
    )


class APIKeyResponse(BaseModel):
    """
    Response schema for API key data (without the actual key).
    
    The full key is only shown once when created.
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID = Field(description="Unique API key identifier")
    tenant_id: uuid.UUID = Field(description="Parent tenant ID")
    environment_id: uuid.UUID = Field(description="Associated environment ID")
    name: str = Field(description="Human-readable name")
    key_prefix: str = Field(description="First 12 characters for identification")
    is_active: bool = Field(description="Whether the key is currently valid")
    last_used_at: datetime | None = Field(description="Last successful use")
    created_at: datetime
    updated_at: datetime


class APIKeyCreateResponse(APIKeyResponse):
    """
    Response schema when creating an API key.
    
    Includes the full key - THIS IS THE ONLY TIME THE KEY IS VISIBLE.
    """
    
    key: str = Field(
        description="The full API key. SAVE THIS - it cannot be retrieved again!",
    )


class APIKeyUpdate(BaseModel):
    """Request schema for updating an API key."""
    
    name: str | None = Field(default=None, min_length=2, max_length=100)
    is_active: bool | None = Field(default=None)
