import json
import logging
import os
from typing import Any, Dict, List, Optional
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

class InMemoryRedisMock:
    """Fallback in-memory mock for when Redis is unavailable."""
    def __init__(self):
        self._data: Dict[str, str] = {}
        self._queues: Dict[str, List[str]] = {}
        logger.warning("Using in-memory dictionary instead of actual Redis server.")

    async def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self._data[key] = value
        # Simple ex handling if needed (ignored for local debugging)
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                count += 1
        return count

    async def rpush(self, key: str, *values: str) -> int:
        if key not in self._queues:
            self._queues[key] = []
        for val in values:
            if val not in self._queues[key]:  # Ensure uniqueness in queue
                self._queues[key].append(val)
        return len(self._queues[key])

    async def lrem(self, key: str, count: int, value: str) -> int:
        if key not in self._queues:
            return 0
        original_len = len(self._queues[key])
        self._queues[key] = [v for v in self._queues[key] if v != value]
        return original_len - len(self._queues[key])

    async def llen(self, key: str) -> int:
        return len(self._queues.get(key, []))

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        q = self._queues.get(key, [])
        # Handle python slice notation representing redis lrange
        if end == -1:
            return q[start:]
        return q[start:end+1]

    async def lpop(self, key: str, count: Optional[int] = None) -> Any:
        if key not in self._queues or not self._queues[key]:
            return None if count is None else []
        
        if count is None:
            return self._queues[key].pop(0)
        
        popped = []
        for _ in range(min(count, len(self._queues[key]))):
            popped.append(self._queues[key].pop(0))
        return popped

    async def ping(self) -> bool:
        return True


# Global client instance
redis_client = None

def get_redis_client():
    global redis_client
    if redis_client is not None:
        return redis_client

    if REDIS_URL.lower() == "memory":
        redis_client = InMemoryRedisMock()
        return redis_client

    try:
        # Attempt to connect to real Redis
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        # We wrap ping check in a try-except during runtime or check it lazily.
        redis_client = client
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {REDIS_URL}: {e}. Falling back to in-memory.")
        redis_client = InMemoryRedisMock()

    return redis_client


# Helper wrapper functions
async def set_cache(key: str, val: Any, expire_seconds: Optional[int] = None) -> bool:
    client = get_redis_client()
    try:
        serialized = json.dumps(val)
        await client.set(key, serialized, ex=expire_seconds)
        return True
    except Exception as e:
        logger.error(f"Redis set failed for {key}: {e}")
        # Fallback to in-memory directly if client fails on actual network call
        if not isinstance(client, InMemoryRedisMock):
            fallback = InMemoryRedisMock()
            await fallback.set(key, json.dumps(val))
            globals()['redis_client'] = fallback
            return True
        return False

async def get_cache(key: str) -> Optional[Any]:
    client = get_redis_client()
    try:
        val = await client.get(key)
        if val is None:
            return None
        return json.loads(val)
    except Exception as e:
        logger.error(f"Redis get failed for {key}: {e}")
        return None

async def delete_cache(key: str) -> bool:
    client = get_redis_client()
    try:
        await client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Redis delete failed for {key}: {e}")
        return False
