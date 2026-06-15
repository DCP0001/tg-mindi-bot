import uuid
from typing import List, Optional, Dict, Any
from mindi.cache.redis_client import get_redis_client, set_cache, get_cache

QUEUE_KEY_PREFIX = "mindi:queue:"
PLAYER_INFO_PREFIX = "mindi:player_info:"

async def add_to_queue(player_id: int, player_name: str, mode: str) -> int:
    """Adds a player to the queue for the specified mode. Returns current queue length."""
    client = get_redis_client()
    queue_key = f"{QUEUE_KEY_PREFIX}{mode.lower()}"
    
    # Store player info (name)
    await set_cache(f"{PLAYER_INFO_PREFIX}{player_id}", {"name": player_name})
    
    # Add to list
    await client.rpush(queue_key, str(player_id))
    return await client.llen(queue_key)

async def remove_from_queue(player_id: int, mode: str) -> bool:
    """Removes a player from the queue."""
    client = get_redis_client()
    queue_key = f"{QUEUE_KEY_PREFIX}{mode.lower()}"
    removed_count = await client.lrem(queue_key, 0, str(player_id))
    return removed_count > 0

async def get_queue_players(mode: str) -> List[int]:
    """Returns the list of player IDs in the queue."""
    client = get_redis_client()
    queue_key = f"{QUEUE_KEY_PREFIX}{mode.lower()}"
    raw_ids = await client.lrange(queue_key, 0, -1)
    return [int(pid) for pid in raw_ids]

async def check_and_create_match(mode: str) -> Optional[Dict[str, Any]]:
    """
    Checks if there are at least 4 players in the queue.
    If so, pops 4 players, creates a new game session state, and returns the details.
    """
    client = get_redis_client()
    queue_key = f"{QUEUE_KEY_PREFIX}{mode.lower()}"
    
    queue_len = await client.llen(queue_key)
    if queue_len < 4:
        return None
        
    # Pop 4 player IDs from the queue
    popped_ids = await client.lpop(queue_key, count=4)
    if not popped_ids or len(popped_ids) < 4:
        # Put back if pop failed to get 4 (race condition fallback)
        if popped_ids:
            for pid in popped_ids:
                await client.rpush(queue_key, pid)
        return None

    player_ids = [int(pid) for pid in popped_ids]
    player_names = []
    
    for pid in player_ids:
        info = await get_cache(f"{PLAYER_INFO_PREFIX}{pid}")
        name = info.get("name", f"Player {pid}") if info else f"Player {pid}"
        player_names.append(name)
        
    match_id = f"MND-{uuid.uuid4().hex[:6].upper()}"
    
    return {
        "match_id": match_id,
        "player_ids": player_ids,
        "player_names": player_names,
        "mode": mode.lower()
    }
