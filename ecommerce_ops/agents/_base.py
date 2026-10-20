import abc
from typing import Any

import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ecommerce_ops.config import Environment, settings
from ecommerce_ops.graph.state import AgentDecision
from ecommerce_ops.memory.agent_memory import (
    get_pattern_insight,
    get_recent_memories,
    store_decision_memory,
)
from ecommerce_ops.memory.vector.agent_integration import agent_memory_manager
from ecommerce_ops.memory.vector.retrieval import memory_retrieval

logger = structlog.get_logger(__name__)


class _DisabledLLM:
    """Hermetic test fallback that fails fast with zero network I/O.

    Used in TESTING so tests stay deterministic regardless of ambient API
    keys (a developer shell may export real GOOGLE_API_KEY / DEEPSEEK_API_KEY).
    Raises a structured failure the same way a provider outage would, so
    callers still exercise their documented rule-based fallback paths.
    """

    def __init__(self, model: str, temperature: int = 0, timeout: int = 30) -> None:
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def with_structured_output(self, *args: Any, **kwargs: Any) -> "_DisabledLLM":
        return self

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            "LLM disabled in TESTING environment (hermetic guard); configure a "
            "real provider key in a non-testing environment."
        )


def _build_memory_query(agent_name: str, state: dict[str, Any]) -> str:
    """Build a semantic query string from the current agent state snapshot."""
    parts = [f"{agent_name} operational decision"]

    for key in ("active_orders", "inventory_data", "reviews_data"):
        items = state.get(key)
        if isinstance(items, list):
            for item in items[:3]:
                if isinstance(item, dict):
                    sku = item.get("sku")
                    if sku:
                        parts.append(sku)
                    content = item.get("content")
                    if isinstance(content, str) and content:
                        parts.append(content[:120])
                elif isinstance(item, str):
                    parts.append(item[:120])

    return " ".join(parts[:20])


class BaseAgent(abc.ABC):  # noqa: B024
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        google_key = settings.GOOGLE_API_KEY.get_secret_value() if settings.GOOGLE_API_KEY else None
        deepseek_key = (
            settings.DEEPSEEK_API_KEY.get_secret_value() if settings.DEEPSEEK_API_KEY else None
        )
        if settings.ENV == Environment.TESTING:
            self.llm = _DisabledLLM(model=settings.LLM_MODEL, temperature=0, timeout=30)
        elif google_key:
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=google_key,
                temperature=0,
                timeout=30,
            )
        elif deepseek_key:
            self.llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                openai_api_key=deepseek_key,
                openai_api_base=settings.DEEPSEEK_BASE_URL,
                temperature=0,
                timeout=30,
            )
        else:
            if settings.ENV == Environment.PRODUCTION:
                raise RuntimeError(
                    f"No LLM API key configured for agent {agent_name}. Set GOOGLE_API_KEY or DEEPSEEK_API_KEY."
                )
            # Development fallback - uses settings.LLM_MODEL which defaults to gemini-2.0-flash
            # but requires a valid key. This will fail at first call if no key is set.
            self.llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                openai_api_key="sk-dummy-key-do-not-use-in-prod",
                temperature=0,
                timeout=30,
            )

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement 'run' or use a custom method"
        )

    async def load_memory_context(self, state: dict[str, Any]) -> str:
        recent = await get_recent_memories(self.agent_name, 5)
        insight = await get_pattern_insight(self.agent_name)
        lines = []
        if recent:
            lines.append("Recent decisions from this agent:")
            for m in recent:
                lines.append(
                    f"  - {m.get('action_type')} | conf={m.get('confidence')} | "
                    f"approval={'needed' if m.get('requires_approval') else 'auto'} | "
                    f"{m.get('reasoning', '')[:80]}"
                )
        if insight:
            lines.append(f"Pattern insight: {insight}")
        vector_context = await self._load_vector_context(state)
        if vector_context:
            lines.append("Relevant knowledge:\n" + vector_context)
        return "\n".join(lines) if lines else ""

    async def _load_vector_context(self, state: dict[str, Any]) -> str:
        """Pull durable, semantically-relevant vector memories into the prompt."""
        query = _build_memory_query(self.agent_name, state)
        try:
            return await memory_retrieval.get_context_window(
                query=query,
                agent_name=self.agent_name,
                max_tokens=1000,
            )
        except Exception as e:  # pragma: no cover - fail-open, never blocks inference
            logger.warning("vector memory unavailable for %s: %s", self.agent_name, e)
            return ""

    async def persist_decision(self, decision: AgentDecision) -> None:
        await store_decision_memory(
            self.agent_name,
            {
                "action_type": decision.action_type,
                "confidence_score": decision.confidence_score,
                "reasoning": decision.reasoning,
                "requires_approval": decision.requires_approval,
            },
        )
        try:
            await agent_memory_manager.store_decision(
                agent_name=self.agent_name,
                decision_type=decision.action_type,
                reasoning=decision.reasoning,
                outcome=(
                    "sent_to_review" if decision.requires_approval else "executed_automatically"
                ),
                confidence=decision.confidence_score,
                metadata={"requires_approval": decision.requires_approval},
            )
        except Exception as e:  # pragma: no cover - fail-open, never blocks inference
            logger.warning("durable memory write failed for %s: %s", self.agent_name, e)

    def create_decision(
        self,
        action_type: str,
        reasoning: str,
        data: dict[str, Any],
        confidence: float,
        requires_approval: bool = True,
    ) -> AgentDecision:
        return AgentDecision(
            agent_id=self.agent_name,
            action_type=action_type,
            reasoning=reasoning,
            action_data=data,
            confidence_score=confidence,
            requires_approval=requires_approval,
        )
