"""
Pydantic Schemas for Feature Flags.

This module defines the request/response schemas for flag operations.
Includes schemas for flag CRUD and evaluation endpoints.

Key Design Decisions:
    - Separate Create/Update schemas for different validation rules
    - Response schemas hide internal fields
    - Evaluation schemas optimized for minimal payload size
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# Flag Schemas
# =============================================================================

class FlagBase(BaseModel):
    """Base schema with common flag fields."""
    
    key: str = Field(
        ...,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="Machine-readable key (lowercase, hyphens allowed)",
        examples=["dark-mode", "new-checkout-flow", "beta-feature"],
    )
    
    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Human-readable name",
        examples=["Dark Mode", "New Checkout Flow"],
    )
    
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Detailed description of the flag's purpose",
    )


class FlagCreate(FlagBase):
    """
    Request schema for creating a new feature flag.
    
    Example:
        POST /api/v1/flags
        {
            "key": "dark-mode",
            "name": "Dark Mode",
            "description": "Enable dark theme for users",
            "rollout_percentage": 10,
            "is_enabled": true
        }
    """
    
    rollout_percentage: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Percentage of users who see the feature (0-100)",
    )
    
    is_enabled: bool = Field(
        default=True,
        description="Master switch - if false, flag always evaluates to false",
    )
    
    tags: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata tags",
        examples=[{"team": "payments", "ticket": "JIRA-123"}],
    )
    
    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Ensure key is lowercase."""
        return v.lower()


class FlagUpdate(BaseModel):
    """
    Request schema for updating a feature flag.
    
    All fields are optional. Key cannot be changed after creation.
    
    Example:
        PATCH /api/v1/flags/{key}
        {
            "rollout_percentage": 50,
            "description": "Updated description"
        }
    """
    
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )
    
    description: str | None = Field(
        default=None,
        max_length=1000,
    )
    
    rollout_percentage: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    
    is_enabled: bool | None = Field(default=None)
    
    tags: dict[str, Any] | None = Field(default=None)
    
    status: str | None = Field(
        default=None,
        pattern=r"^(active|inactive|archived)$",
        description="Flag status: active, inactive, or archived",
    )


class FlagResponse(FlagBase):
    """
    Response schema for flag data.
    
    Returned from GET/POST/PATCH endpoints.
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID = Field(description="Unique flag identifier")
    tenant_id: uuid.UUID = Field(description="Owning tenant ID")
    rollout_percentage: int = Field(description="Rollout percentage (0-100)")
    is_enabled: bool = Field(description="Whether the flag is enabled")
    status: str = Field(description="Current status")
    tags: dict[str, Any] | None = Field(description="Metadata tags")
    created_at: datetime
    updated_at: datetime


class FlagListResponse(BaseModel):
    """
    Response schema for listing flags.
    
    Includes pagination metadata.
    """
    
    items: list[FlagResponse] = Field(description="List of flags")
    total: int = Field(description="Total number of flags")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")
    pages: int = Field(description="Total number of pages")


# =============================================================================
# Audit Log Schemas
# =============================================================================

class FlagAuditLogResponse(BaseModel):
    """Response schema for flag audit log entries."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID = Field(description="Audit log entry ID")
    flag_id: uuid.UUID = Field(description="Associated flag ID")
    action: str = Field(description="Type of action performed")
    changes: dict[str, Any] = Field(description="Before/after values")
    actor_id: uuid.UUID | None = Field(description="User who made the change")
    actor_email: str | None = Field(description="Email of the actor")
    created_at: datetime = Field(description="When the change occurred")


# =============================================================================
# SDK / Bulk Configuration Schemas
# =============================================================================

class FlagConfigItem(BaseModel):
    """
    Minimal flag configuration for SDK bootstrap.
    
    Optimized for payload size - only includes fields needed for evaluation.
    """
    
    key: str = Field(description="Flag key")
    rollout_percentage: int = Field(description="Rollout percentage")
    is_enabled: bool = Field(description="Whether the flag is enabled")


class FlagConfigResponse(BaseModel):
    """
    Response schema for SDK configuration endpoint.
    
    Returns all flags for a tenant/environment for SDK initialization.
    
    Example response:
        {
            "flags": [
                {"key": "dark-mode", "rollout_percentage": 100, "is_enabled": true},
                {"key": "new-checkout", "rollout_percentage": 25, "is_enabled": true}
            ],
            "environment": "production",
            "generated_at": "2024-01-15T10:30:00Z"
        }
    """
    
    flags: list[FlagConfigItem] = Field(description="All active flags")
    environment: str = Field(description="Environment key")
    generated_at: datetime = Field(description="When this config was generated")
