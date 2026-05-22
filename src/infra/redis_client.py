"""
Agent-OS Redis Layer
Distributed rate limiting, session caching, pub/sub for multi-instance coordination.
Falls back gracefully to in-memory when Redis is unavailable.
"""
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("agent-os.infra.redis")


class InMemoryFallback:
    """In-memory fallback when Redis is unavailable. NOT distributed."""

    MAX_KEYS = 10000  # Hard cap to prevent unbounded memory growth

    def __init__(self):
        self._data: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expiry_timestamp)
        self._sorted_sets: Dict[str, Dict[str, float]] = defaultdict(dict)

    def _evict_if_needed(self):
        """Evict expired and oldest entries if over MAX_KEYS."""
        now = time.time()
        # First pass: remove expired
        expired = [k for k, (_, exp) in self._data.items() if 0 < exp < now]
        for k in expired:
            del self._data[k]
        # If still over limit, remove oldest entries
        if len(self._data) > self.MAX_KEYS:
            sorted_keys = sorted(self._data.keys(), key=lambda k: self._data[k][1] or 0)
            for k in sorted_keys[:len(self._data) - self.MAX_KEYS]:
                del self._data[k]

    async def get(self, key: str) -> Optional[str]:
        val = self._data.get(key)
        if val is None:
            return None
        value, expiry = val
        if expiry > 0 and time.time() > expiry:
            del self._data[key]
            return None
        return value

    async def set(self, key: str, value: str, ex: int = 0):
        expiry = time.time() + ex if ex > 0 else 0
        self._data[key] = (value, expiry)
        self._evict_if_needed()

    async def delete(self, key: str):
        self._data.pop(key, None)

    async def incr(self, key: str) -> int:
        val = await self.get(key)
        new_val = (int(val) if val else 0) + 1
        await self.set(key, str(new_val))
        return new_val

    async def expire(self, key: str, seconds: int):
        if key in self._data:
            value, _ = self._data[key]
            self._data[key] = (value, time.time() + seconds)

    async def ttl(self, key: str) -> int:
        val = self._data.get(key)
        if val is None:
            return -2
        _, expiry = val
        if expiry <= 0:
            return -1
        remaining = int(expiry - time.time())
        return max(remaining, -2)

    async def zadd(self, key: str, mapping: dict):
        self._sorted_sets[key].update(mapping)

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float):
        if key in self._sorted_sets:
            self._sorted_sets[key] = {
                k: v for k, v in self._sorted_sets[key].items()
                if not (min_score <= v <= max_score)
            }

    async def zcard(self, key: str) -> int:
        return len(self._sorted_sets.get(key, {}))

    async def keys(self, pattern: str = "*") -> list:
        import fnmatch
        return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]

    async def flushdb(self):
        self._data.clear()
        self._sorted_sets.clear()

    async def ping(self) -> bool:
        return True

    async def close(self):
        """Clean up in-memory fallback resources."""
        self._data.clear()
        self._sorted_sets.clear()


class RedisClient:
    """
    Redis client with automatic fallback to in-memory.
    Provides: distributed rate limiting, session caching, distributed locks.
    """

    def __init__(self, url: str = "redis://localhost:6379/0", fallback_on_failure: bool = True):
        self.url = url
        self._url = url
        self._redis = None
        self._fallback = InMemoryFallback()
        self._use_fallback = True
        self._fallback_on_failure = fallback_on_failure
        self._connected = False
        self._mode = "memory"  # Track current mode: "redis" or "memory"

    @property
    def is_fallback(self) -> bool:
        """True if using in-memory fallback instead of real Redis."""
        return self._use_fallback

    async def connect(self):
        """Connect to Redis, fall back to in-memory if unavailable."""
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                max_connections=50,
            )
            await self._redis.ping()
            self._use_fallback = False
            self._connected = True
            self._mode = "redis"
            logger.info(f"Connected to Redis: {self.url}")
        except Exception as e:
            if self._fallback_on_failure:
                logger.warning(
                    f"Redis unavailable ({e}). "
                    f"Using in-memory fallback — rate limiting and distributed features "
                    f"will work per-process only (not shared across instances). "
                    f"For production multi-instance deployments, configure Redis."
                )
                self._use_fallback = True
                self._connected = True
            else:
                raise

    async def disconnect(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
        self._connected = False

    @property
    def _backend(self):
        return self._fallback if self._use_fallback else self._redis

    async def _ensure_connected(self) -> bool:
        """Ensure Redis connection is alive, reconnect if needed with exponential backoff."""
        if self._mode != "redis" or self._redis is None:
            return False
        try:
            await self._redis.ping()
            return True
        except Exception:
            # Try to reconnect with exponential backoff
            for attempt in range(3):
                try:
                    await asyncio.sleep(min(2 ** attempt, 10))
                    import redis.asyncio as aioredis
                    self._redis = aioredis.from_url(
                        self._url,
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                        retry_on_timeout=True,
                        max_connections=50,
                    )
                    await self._redis.ping()
                    logger.info("Redis reconnected successfully")
                    return True
                except Exception:
                    continue
            logger.error("Redis reconnection failed after 3 attempts, using in-memory fallback")
            self._use_fallback = True
            self._mode = "memory"
            return False

    async def health_check(self) -> dict:
        """Check Redis connectivity."""
        start = time.time()
        try:
            # If we think we're in redis mode, verify the connection first
            if not self._use_fallback and self._redis is not None:
                await self._ensure_connected()
            backend = self._backend
            await backend.ping()
            return {
                "status": "healthy",
                "mode": "memory" if self._use_fallback else "redis",
                "latency_ms": round((time.time() - start) * 1000, 2),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    # ─── Rate Limiting (Sliding Window) ──────────────────────

    async def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, int]:
        """
        Sliding window rate limiter.
        Returns: (allowed, current_count, remaining)
        """
        now = time.time()
        window_key = f"rl:{key}"

        if self._use_fallback:
            # In-memory sliding window
            bucket = self._fallback._sorted_sets.get(window_key, {})
            cutoff = now - window_seconds
            # Clean old entries
            bucket = {k: v for k, v in bucket.items() if v > cutoff}
            count = len(bucket)
            if count >= max_requests:
                return False, count, 0
            bucket[f"{now}:{count}"] = now
            self._fallback._sorted_sets[window_key] = bucket
            return True, count + 1, max_requests - count - 1
        else:
            # Redis sorted set sliding window
            pipe = self._redis.pipeline()
            cutoff = now - window_seconds
            pipe.zremrangebyscore(window_key, 0, cutoff)
            pipe.zcard(window_key)
            pipe.zadd(window_key, {f"{now}": now})
            pipe.expire(window_key, window_seconds)
            results = await pipe.execute()
            count = results[1]
            if count >= max_requests:
                return False, count, 0
            return True, count + 1, max_requests - count - 1

    # ─── Session Cache ───────────────────────────────────────

    async def cache_session(self, session_id: str, data: dict, ttl: int = 900):
        """Cache session data with TTL (default 15 min)."""
        await self._backend.set(f"session:{session_id}", json.dumps(data), ex=ttl)

    async def get_cached_session(self, session_id: str) -> Optional[dict]:
        """Get cached session data."""
        raw = await self._backend.get(f"session:{session_id}")
        return json.loads(raw) if raw else None

    async def invalidate_session(self, session_id: str):
        """Remove session from cache."""
        await self._backend.delete(f"session:{session_id}")

    # ─── Distributed Lock ────────────────────────────────────

    async def acquire_lock(self, resource: str, owner: str, ttl: int = 30) -> bool:
        """Acquire a distributed lock. Returns True if acquired."""
        key = f"lock:{resource}"
        if self._use_fallback:
            existing = await self._fallback.get(key)
            if existing:
                return False
            await self._fallback.set(key, owner, ex=ttl)
            return True
        else:
            result = await self._redis.set(key, owner, ex=ttl, nx=True)
            return result is True

    async def release_lock(self, resource: str, owner: str) -> bool:
        """Release a distributed lock (only if owned)."""
        key = f"lock:{resource}"
        if self._use_fallback:
            existing = await self._fallback.get(key)
            if existing == owner:
                await self._fallback.delete(key)
                return True
            return False
        else:
            # Lua script for atomic check-and-delete
            lua = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            end
            return 0
            """
            result = await self._redis.eval(lua, 1, key, owner)
            return result == 1

    # ─── Generic Helpers ─────────────────────────────────────

    async def get(self, key: str) -> Optional[str]:
        return await self._backend.get(key)

    async def set(self, key: str, value: str, ex: int = 0):
        await self._backend.set(key, value, ex=ex)

    async def delete(self, key: str):
        await self._backend.delete(key)

    async def incr(self, key: str) -> int:
        return await self._backend.incr(key)

    async def keys(self, pattern: str = "*") -> list:
        return await self._backend.keys(pattern)


# Global instance
_redis: Optional[RedisClient] = None


def get_redis() -> RedisClient:
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis


def init_redis(url: str = "redis://localhost:6379/0", **kwargs) -> RedisClient:
    global _redis
    _redis = RedisClient(url, **kwargs)
    return _redis
