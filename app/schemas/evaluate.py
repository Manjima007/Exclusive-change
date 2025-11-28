"""
Pydantic Schemas for Flag Evaluation.

This module defines the request/response schemas for the high-performance
evaluation API used by SDKs and clients.

Design Goals:
    - Minimal payload size for low latency
    - Simple request/response structure
    - Support for single and bulk evaluation
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Evaluation Context
# =============================================================================

class EvaluationContext(BaseModel):
    """
    User context for flag evaluation.
    
    The user_id is required for deterministic percentage rollout.
    Additional attributes can be included for future targeting rules.
    
    Example:
        {
            "user_id": "user-12345",
            "attributes": {
                "email": "user@example.com",
                "plan": "premium",
                "country": "US"
            }
        }
    """
    
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Unique user identifier for consistent hashing",
        examples=["user-12345", "550e8400-e29b-41d4-a716-446655440000"],
    )
    
    attributes: dict[str, Any] | None = Field(
        default=None,
        description="Additional user attributes for targeting (future use)",
        examples=[{"plan": "premium", "country": "US"}],
    )


# =============================================================================
# Single Flag Evaluation
# =============================================================================

class EvaluateFlagRequest(BaseModel):
    """
    Request schema for evaluating a single feature flag.
    
    Example:
        POST /api/v1/evaluate
        {
            "flag_key": "dark-mode",
            "context": {
                "user_id": "user-12345"
            }
        }
    """
    
    flag_key: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="The flag key to evaluate",
        examples=["dark-mode", "new-checkout-flow"],
    )
    
    context: EvaluationContext = Field(
        ...,
        description="User context for evaluation",
    )
    
    default_value: bool = Field(
        default=False,
        description="Value to return if flag is not found or disabled",
    )


class EvaluateFlagResponse(BaseModel):
    """
    Response schema for single flag evaluation.
    
    Example:
        {
            "flag_key": "dark-mode",
            "value": true,
            "reason": "ROLLOUT_MATCH"
        }
    """
    
    flag_key: str = Field(description="The evaluated flag key")
    value: bool = Field(description="Evaluation result (true/false)")
    reason: str = Field(
        description="Reason for the evaluation result",
        examples=["ROLLOUT_MATCH", "ROLLOUT_NO_MATCH", "FLAG_DISABLED", "FLAG_NOT_FOUND"],
    )


# =============================================================================
# Bulk Flag Evaluation
# =============================================================================

class EvaluateBulkRequest(BaseModel):
    """
    Request schema for evaluating multiple flags at once.
    
    More efficient than multiple single evaluations when SDK needs
    to check several flags for the same user.
    
    Example:
        POST /api/v1/evaluate/bulk
        {
            "flag_keys": ["dark-mode", "new-checkout", "beta-feature"],
            "context": {
                "user_id": "user-12345"
            }
        }
    """
    
    flag_keys: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,  # Limit to prevent abuse
        description="List of flag keys to evaluate",
    )
    
    context: EvaluationContext = Field(
        ...,
        description="User context for evaluation",
    )
    
    default_value: bool = Field(
        default=False,
        description="Default value for flags not found",
    )


class BulkEvaluationResult(BaseModel):
    """Single flag result within a bulk evaluation response."""
    
    flag_key: str = Field(description="The evaluated flag key")
    value: bool = Field(description="Evaluation result")
    reason: str = Field(description="Reason for the result")


class EvaluateBulkResponse(BaseModel):
    """
    Response schema for bulk flag evaluation.
    
    Example:
        {
            "results": [
                {"flag_key": "dark-mode", "value": true, "reason": "ROLLOUT_MATCH"},
                {"flag_key": "new-checkout", "value": false, "reason": "ROLLOUT_NO_MATCH"}
            ],
            "evaluated_at": "2024-01-15T10:30:00Z"
        }
    """
    
    results: list[BulkEvaluationResult] = Field(
        description="Evaluation results for each flag",
    )
    evaluated_at: datetime = Field(
        description="Timestamp of evaluation",
    )


# =============================================================================
# All Flags Evaluation (SDK Bootstrap)
# =============================================================================

class EvaluateAllRequest(BaseModel):
    """
    Request schema for evaluating all flags for a user.
    
    Used by SDKs during initialization to get the full flag state.
    
    Example:
        POST /api/v1/evaluate/all
        {
            "context": {
                "user_id": "user-12345"
            }
        }
    """
    
    context: EvaluationContext = Field(
        ...,
        description="User context for evaluation",
    )


class EvaluateAllResponse(BaseModel):
    """
    Response schema for evaluating all flags.
    
    Returns a map of flag_key -> boolean value for easy SDK consumption.
    
    Example:
        {
            "flags": {
                "dark-mode": true,
                "new-checkout": false,
                "beta-feature": true
            },
            "environment": "production",
            "evaluated_at": "2024-01-15T10:30:00Z"
        }
    """
    
    flags: dict[str, bool] = Field(
        description="Map of flag_key to evaluation result",
    )
    environment: str = Field(
        description="Environment the flags were evaluated in",
    )
    evaluated_at: datetime = Field(
        description="Timestamp of evaluation",
    )
