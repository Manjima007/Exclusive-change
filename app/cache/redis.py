"""
Redis Caching Layer.

This module provides async Redis operations for caching feature flags.
It implements both TTL-based caching and pub/sub for instant invalidation.

Caching Strategy:
    - Cache key format: "flags:{tenant_id}:{environment_key}"
    - TTL: Configurable (default 30 seconds) as safety net
    - Pub/Sub: Instant invalidation on flag updates

Cache Structure:
    The cache stores flag data as JSON for easy serialization:
    {
        "flags": {
            "dark-mode": {"rollout_percentage": 100, "is_enabled": true},
            "new-checkout": {"rollout_percentage": 25, "is_enabled": true}
        },
        "cached_at": "2024-01-15T10:30:00Z"
    }
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import settings
from app.core.exceptions import CacheError

logger = logging.getLogger(__name__)


class RedisCache:
    """
    Async Redis cache client for feature flags.
    
    Provides high-level caching operations with automatic serialization,
    TTL management, and pub/sub for cache invalidation.
    
    Usage:
        cache = RedisCache()
        await cache.connect()
        
        # Store flags
        await cache.set_flags(tenant_id, "production", flags_data)
        
        # Retrieve flags
        flags = await cache.get_flags(tenant_id, "production")
        
        # Invalidate on update
        await cache.invalidate_flags(tenant_id, "production")
    """
    
    def __init__(self) -> None:
        """Initialize Redis cache (call connect() before use)."""
        self._client: Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
    
    @property
    def client(self) -> Redis:
        """Get the Redis client, raising if not connected."""
        if self._client is None:
            raise CacheError("Redis client not connected. Call connect() first.")
        return self._client
    
    async def connect(self) -> None:
        """
        Establish connection to Redis.
        
        Called during application startup to verify Redis connectivity.
        
        Raises:
            CacheError: If connection fails.
        """
        try:
            self._client = redis.from_url(
                str(settings.REDIS_URL),
                encoding="utf-8",
                decode_responses=True,
            )
            # Verify connection
            await self._client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise CacheError(f"Redis connection failed: {e}")
    
    async def disconnect(self) -> None:
        """Close Redis connection (call during shutdown)."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")
    
    # =========================================================================
    # Cache Key Generation
    # =========================================================================
    
    def _flags_key(self, tenant_id: uuid.UUID, environment_key: str) -> str:
        """Generate cache key for flags."""
        return f"flags:{tenant_id}:{environment_key}"
    
    def _flag_key(self, tenant_id: uuid.UUID, flag_key: str) -> str:
        """Generate cache key for a single flag."""
        return f"flag:{tenant_id}:{flag_key}"
    
    def _invalidation_channel(self) -> str:
        """Get the pub/sub channel for cache invalidation."""
        return "cache:invalidate"
    
    # =========================================================================
    # Flag Caching Operations
    # =========================================================================
    
    async def get_flags(
        self,
        tenant_id: uuid.UUID,
        environment_key: str,
    ) -> dict[str, Any] | None:
        """
        Get cached flags for a tenant/environment.
        
        Args:
            tenant_id: Tenant ID.
            environment_key: Environment key (e.g., "production").
        
        Returns:
            Cached flag data if exists, None otherwise.
        """
        try:
            key = self._flags_key(tenant_id, environment_key)
            data = await self.client.get(key)
            
            if data:
                logger.debug(f"Cache HIT for {key}")
                return json.loads(data)
            
            logger.debug(f"Cache MISS for {key}")
            return None
            
        except Exception as e:
            # Cache errors are non-fatal - log and continue
            logger.warning(f"Cache get failed: {e}")
            return None
    
    async def set_flags(
        self,
        tenant_id: uuid.UUID,
        environment_key: str,
        flags: list[dict[str, Any]],
    ) -> None:
        """
        Cache flags for a tenant/environment.
        
        Args:
            tenant_id: Tenant ID.
            environment_key: Environment key.
            flags: List of flag data to cache.
        """
        try:
            key = self._flags_key(tenant_id, environment_key)
            
            # Structure the cache data
            cache_data = {
                "flags": {f["key"]: f for f in flags},
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            
            await self.client.setex(
                key,
                settings.CACHE_TTL_SECONDS,
                json.dumps(cache_data),
            )
            logger.debug(f"Cached flags for {key}")
            
        except Exception as e:
            # Cache errors are non-fatal
            logger.warning(f"Cache set failed: {e}")
    
    async def get_flag(
        self,
        tenant_id: uuid.UUID,
        flag_key: str,
    ) -> dict[str, Any] | None:
        """
        Get a single cached flag.
        
        Args:
            tenant_id: Tenant ID.
            flag_key: The flag's key.
        
        Returns:
            Cached flag data if exists, None otherwise.
        """
        try:
            key = self._flag_key(tenant_id, flag_key)
            data = await self.client.get(key)
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None
    
    async def set_flag(
        self,
        tenant_id: uuid.UUID,
        flag_key: str,
        flag_data: dict[str, Any],
    ) -> None:
        """
        Cache a single flag.
        
        Args:
            tenant_id: Tenant ID.
            flag_key: The flag's key.
            flag_data: Flag data to cache.
        """
        try:
            key = self._flag_key(tenant_id, flag_key)
            await self.client.setex(
                key,
                settings.CACHE_TTL_SECONDS,
                json.dumps(flag_data),
            )
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
    
    # =========================================================================
    # Cache Invalidation
    # =========================================================================
    
    async def invalidate_flags(
        self,
        tenant_id: uuid.UUID,
        environment_key: str | None = None,
    ) -> None:
        """
        Invalidate cached flags for a tenant.
        
        If environment_key is provided, only that environment's cache is
        invalidated. Otherwise, all environments for the tenant are cleared.
        
        Args:
            tenant_id: Tenant ID.
            environment_key: Optional environment to invalidate.
        """
        try:
            if environment_key:
                # Invalidate specific environment
                key = self._flags_key(tenant_id, environment_key)
                await self.client.delete(key)
                logger.debug(f"Invalidated cache for {key}")
            else:
                # Invalidate all environments for tenant
                pattern = f"flags:{tenant_id}:*"
                async for key in self.client.scan_iter(match=pattern):
                    await self.client.delete(key)
                logger.debug(f"Invalidated all caches for tenant {tenant_id}")
            
            # Publish invalidation event for distributed systems
            await self._publish_invalidation(tenant_id, environment_key)
            
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")
    
    async def invalidate_flag(
        self,
        tenant_id: uuid.UUID,
        flag_key: str,
    ) -> None:
        """
        Invalidate a single cached flag.
        
        Args:
            tenant_id: Tenant ID.
            flag_key: The flag's key.
        """
        try:
            key = self._flag_key(tenant_id, flag_key)
            await self.client.delete(key)
            logger.debug(f"Invalidated cache for {key}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")
    
    # =========================================================================
    # Pub/Sub for Distributed Invalidation
    # =========================================================================
    
    async def _publish_invalidation(
        self,
        tenant_id: uuid.UUID,
        environment_key: str | None = None,
    ) -> None:
        """
        Publish cache invalidation event.
        
        Used in distributed deployments where multiple app instances
        need to know when to refresh their local caches.
        """
        try:
            message = {
                "type": "invalidate_flags",
                "tenant_id": str(tenant_id),
                "environment_key": environment_key,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await self.client.publish(
                self._invalidation_channel(),
                json.dumps(message),
            )
        except Exception as e:
            logger.warning(f"Failed to publish invalidation: {e}")
    
    async def subscribe_invalidations(self) -> None:
        """
        Subscribe to cache invalidation events.
        
        Used by background tasks to listen for invalidation events
        from other instances. Implement handler logic as needed.
        """
        try:
            self._pubsub = self.client.pubsub()
            await self._pubsub.subscribe(self._invalidation_channel())
            logger.info("Subscribed to cache invalidation channel")
        except Exception as e:
            logger.warning(f"Failed to subscribe to invalidations: {e}")
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health_check(self) -> bool:
        """
        Check Redis connectivity.
        
        Returns:
            True if Redis is reachable, False otherwise.
        """
        try:
            await self.client.ping()
            return True
        except Exception:
            return False


# Singleton instance
cache = RedisCache()


async def get_cache() -> RedisCache:
    """Dependency to get the Redis cache instance."""
    return cache
