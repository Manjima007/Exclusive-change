"""
Flag Evaluation Service.

This module contains the core business logic for evaluating feature flags.
It implements deterministic percentage rollout using MD5 hashing.

Key Algorithm:
    hash_value = MD5(user_id + flag_key) % 100
    if hash_value < rollout_percentage:
        return True (flag is ON for this user)
    else:
        return False (flag is OFF for this user)

This ensures:
    - Same user always gets the same result (sticky sessions)
    - Gradual rollout: increase percentage to include more users
    - No external state needed for evaluation
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import RedisCache
from app.crud.crud_flag import crud_flag
from app.models.flag import Flag, FlagStatus

logger = logging.getLogger(__name__)


class EvaluationReason(str, Enum):
    """Reasons for flag evaluation results."""
    
    # Flag is enabled and user falls within rollout percentage
    ROLLOUT_MATCH = "ROLLOUT_MATCH"
    
    # Flag is enabled but user falls outside rollout percentage
    ROLLOUT_NO_MATCH = "ROLLOUT_NO_MATCH"
    
    # Flag is disabled (is_enabled=False)
    FLAG_DISABLED = "FLAG_DISABLED"
    
    # Flag was not found
    FLAG_NOT_FOUND = "FLAG_NOT_FOUND"
    
    # Flag is not in ACTIVE status
    FLAG_INACTIVE = "FLAG_INACTIVE"
    
    # Error during evaluation, default returned
    EVALUATION_ERROR = "EVALUATION_ERROR"


class EvaluationResult:
    """
    Result of a flag evaluation.
    
    Attributes:
        flag_key: The key of the evaluated flag.
        value: The boolean result (True=ON, False=OFF).
        reason: Why this result was returned.
    """
    
    def __init__(
        self,
        flag_key: str,
        value: bool,
        reason: EvaluationReason,
    ) -> None:
        self.flag_key = flag_key
        self.value = value
        self.reason = reason
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "flag_key": self.flag_key,
            "value": self.value,
            "reason": self.reason.value,
        }


class FlagEvaluator:
    """
    Service for evaluating feature flags.
    
    This class encapsulates the core evaluation logic, including:
        - Deterministic percentage rollout (MD5 hashing)
        - Cache-first lookups with database fallback
        - Consistent evaluation results for the same user
    
    Usage:
        evaluator = FlagEvaluator(db, cache, tenant_id)
        result = await evaluator.evaluate("dark-mode", "user-123")
        print(f"Flag is {'ON' if result.value else 'OFF'}")
    """
    
    def __init__(
        self,
        db: AsyncSession,
        cache: RedisCache,
        tenant_id: uuid.UUID,
    ) -> None:
        """
        Initialize the evaluator.
        
        Args:
            db: Database session for flag lookups.
            cache: Redis cache for faster lookups.
            tenant_id: Tenant context for multi-tenancy.
        """
        self.db = db
        self.cache = cache
        self.tenant_id = tenant_id
    
    # =========================================================================
    # Core Hashing Logic
    # =========================================================================
    
    @staticmethod
    def compute_hash_bucket(user_id: str, flag_key: str) -> int:
        """
        Compute deterministic hash bucket for a user+flag combination.
        
        Uses MD5 to generate a consistent hash, then mods by 100 to get
        a bucket from 0-99. This ensures the same user always gets the
        same bucket for a given flag.
        
        Args:
            user_id: Unique user identifier.
            flag_key: The flag's key.
        
        Returns:
            Integer from 0-99 representing the user's bucket.
        
        Example:
            >>> FlagEvaluator.compute_hash_bucket("user-123", "dark-mode")
            42  # This user is in bucket 42
            
            # If rollout_percentage=50, users in buckets 0-49 get True
            # This user (bucket 42) would get True
        """
        # Concatenate user_id and flag_key
        hash_input = f"{user_id}{flag_key}"
        
        # Compute MD5 hash
        md5_hash = hashlib.md5(hash_input.encode()).hexdigest()
        
        # Convert first 8 hex chars to integer and mod by 100
        hash_int = int(md5_hash[:8], 16)
        bucket = hash_int % 100
        
        return bucket
    
    # =========================================================================
    # Single Flag Evaluation
    # =========================================================================
    
    async def evaluate(
        self,
        flag_key: str,
        user_id: str,
        default_value: bool = False,
    ) -> EvaluationResult:
        """
        Evaluate a single feature flag for a user.
        
        Algorithm:
            1. Look up flag (cache first, then database)
            2. If not found → return default_value
            3. If disabled (is_enabled=False) → return False
            4. If not active status → return False
            5. Compute hash bucket for user
            6. If bucket < rollout_percentage → return True
            7. Otherwise → return False
        
        Args:
            flag_key: The flag's unique key.
            user_id: The user's identifier for consistent hashing.
            default_value: Value to return if flag not found.
        
        Returns:
            EvaluationResult with value and reason.
        
        Example:
            result = await evaluator.evaluate("dark-mode", "user-123")
            if result.value:
                show_dark_mode()
        """
        try:
            # Step 1: Get flag data (cache-first)
            flag_data = await self._get_flag_data(flag_key)
            
            # Step 2: Flag not found
            if flag_data is None:
                logger.debug(f"Flag '{flag_key}' not found for tenant {self.tenant_id}")
                return EvaluationResult(
                    flag_key=flag_key,
                    value=default_value,
                    reason=EvaluationReason.FLAG_NOT_FOUND,
                )
            
            # Step 3: Check if enabled
            if not flag_data.get("is_enabled", False):
                return EvaluationResult(
                    flag_key=flag_key,
                    value=False,
                    reason=EvaluationReason.FLAG_DISABLED,
                )
            
            # Step 4: Check status
            status = flag_data.get("status", FlagStatus.ACTIVE.value)
            if status != FlagStatus.ACTIVE.value:
                return EvaluationResult(
                    flag_key=flag_key,
                    value=False,
                    reason=EvaluationReason.FLAG_INACTIVE,
                )
            
            # Step 5-7: Percentage rollout evaluation
            rollout_percentage = flag_data.get("rollout_percentage", 0)
            bucket = self.compute_hash_bucket(user_id, flag_key)
            
            if bucket < rollout_percentage:
                return EvaluationResult(
                    flag_key=flag_key,
                    value=True,
                    reason=EvaluationReason.ROLLOUT_MATCH,
                )
            else:
                return EvaluationResult(
                    flag_key=flag_key,
                    value=False,
                    reason=EvaluationReason.ROLLOUT_NO_MATCH,
                )
                
        except Exception as e:
            logger.error(f"Error evaluating flag '{flag_key}': {e}")
            return EvaluationResult(
                flag_key=flag_key,
                value=default_value,
                reason=EvaluationReason.EVALUATION_ERROR,
            )
    
    # =========================================================================
    # Bulk Evaluation
    # =========================================================================
    
    async def evaluate_bulk(
        self,
        flag_keys: list[str],
        user_id: str,
        default_value: bool = False,
    ) -> list[EvaluationResult]:
        """
        Evaluate multiple flags for a user.
        
        More efficient than calling evaluate() multiple times as it
        can batch cache/database lookups.
        
        Args:
            flag_keys: List of flag keys to evaluate.
            user_id: The user's identifier.
            default_value: Default value for flags not found.
        
        Returns:
            List of EvaluationResult for each flag.
        """
        results = []
        
        # TODO: Optimize with batch cache lookup
        for flag_key in flag_keys:
            result = await self.evaluate(flag_key, user_id, default_value)
            results.append(result)
        
        return results
    
    async def evaluate_all(
        self,
        user_id: str,
    ) -> dict[str, bool]:
        """
        Evaluate all active flags for a user.
        
        Used by SDKs during initialization to get the complete flag state.
        
        Args:
            user_id: The user's identifier.
        
        Returns:
            Dictionary mapping flag_key to boolean value.
        """
        # Get all active flags from database
        flags = await crud_flag.get_active_flags(self.db, self.tenant_id)
        
        result = {}
        for flag in flags:
            evaluation = await self.evaluate(flag.key, user_id)
            result[flag.key] = evaluation.value
        
        return result
    
    # =========================================================================
    # Flag Data Retrieval
    # =========================================================================
    
    async def _get_flag_data(self, flag_key: str) -> dict[str, Any] | None:
        """
        Get flag data, using cache first with database fallback.
        
        Args:
            flag_key: The flag's key.
        
        Returns:
            Flag data dictionary if found, None otherwise.
        """
        # Try cache first
        cached = await self.cache.get_flag(self.tenant_id, flag_key)
        if cached is not None:
            return cached
        
        # Cache miss - get from database
        flag = await crud_flag.get_by_key(self.db, self.tenant_id, flag_key)
        if flag is None:
            return None
        
        # Convert to dict for caching and evaluation
        flag_data = {
            "key": flag.key,
            "rollout_percentage": flag.rollout_percentage,
            "is_enabled": flag.is_enabled,
            "status": flag.status,
        }
        
        # Cache for next time (async, don't wait)
        await self.cache.set_flag(self.tenant_id, flag_key, flag_data)
        
        return flag_data


async def get_evaluator(
    db: AsyncSession,
    cache: RedisCache,
    tenant_id: uuid.UUID,
) -> FlagEvaluator:
    """
    Factory function to create an evaluator.
    
    Use this with FastAPI's Depends() for dependency injection.
    """
    return FlagEvaluator(db, cache, tenant_id)
