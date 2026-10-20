import json
import logging
from typing import Any, Dict, List, Optional

from ecommerce_ops.memory.cache import cache
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.memory.agent_memory")

MEMORY_TTL = 86400 * 7


async def store_decision_memory(
    agent_id: str, decision: Dict[str, Any], ttl: int = MEMORY_TTL
) -> None:
    key = f"agent_memory:{agent_id}:recent"
    try:
        client = await cache.get_client()
        if client is None:
            return
        entry = {
            "timestamp": utc_now().isoformat(),
            "action_type": decision.get("action_type"),
            "confidence": decision.get("confidence_score"),
            "reasoning": decision.get("reasoning", "")[:200],
            "requires_approval": decision.get("requires_approval", True),
        }
        await client.lpush(key, json.dumps(entry))
        await client.ltrim(key, 0, 49)
        await client.expire(key, ttl)
    except Exception as e:
        logger.debug("Failed to store memory for %s: %s", agent_id, e)


async def get_recent_memories(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    key = f"agent_memory:{agent_id}:recent"
    try:
        client = await cache.get_client()
        if client is None:
            return []
        raw = await client.lrange(key, 0, limit - 1)
        return [json.loads(r) for r in raw]
    except Exception as e:
        logger.debug("Failed to retrieve memory for %s: %s", agent_id, e)
        return []


async def get_pattern_insight(agent_id: str) -> Optional[str]:
    memories = await get_recent_memories(agent_id, 20)
    if len(memories) < 5:
        return None

    approved_count = sum(1 for m in memories if not m.get("requires_approval", True))
    high_conf_count = sum(1 for m in memories if (m.get("confidence") or 0) > 0.85)

    if approved_count / max(len(memories), 1) > 0.8 and high_conf_count > len(memories) // 2:
        return "Your recent decisions have been consistently high-confidence and low-risk. Continue current approach."

    return "Mix of approval levels detected. Ensure each decision is well-reasoned."
