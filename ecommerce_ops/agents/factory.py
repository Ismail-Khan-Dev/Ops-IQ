"""Agent Factory

Unified interface for LLM and rule-based agents with automatic fallback.
Tries LLM agent first; on failure, falls back to rule-based agent.

Now driven by the dynamic ``AgentRegistry`` — adding a new agent is a
YAML spec + a Python class.  Zero factory edits required.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from ecommerce_ops.agents.registry import AgentSpec, agent_registry
from ecommerce_ops.observability.agent_metrics import (
    AgentExecutionRecord,
    agent_metrics,
)

logger = logging.getLogger("ecommerce_ops.agents.factory")


class AgentFactory:
    """Creates ``UnifiedAgent`` instances driven by the agent registry.

    Thread-safe with double-checked locking.  Agents are lazily created
    on first ``get_agent(name)`` call.  Call ``reload()`` to pick up
    new/changed YAML specs at runtime.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, UnifiedAgent] = {}
        self._lock = threading.Lock()
        self._ensure_registry_loaded()

    def _ensure_registry_loaded(self) -> None:
        """Scan the specs directory once (idempotent)."""
        if len(agent_registry) == 0:
            agent_registry.scan()

    def get_agent(self, name: str) -> UnifiedAgent:
        """Get or create an agent instance."""
        agent = self._agents.get(name)
        if agent is not None:
            return agent
        with self._lock:
            agent = self._agents.get(name)
            if agent is None:
                agent = self._build_unified(name)
                self._agents[name] = agent
        return agent

    def reload(self) -> Dict[str, Any]:
        """Re-scan specs and rebuild all cached agents.

        Returns a summary dict with ``loaded``, ``errors``, ``agents``.
        """
        with self._lock:
            agent_registry.scan()
            self._agents.clear()
            loaded = list(agent_registry.specs.keys())
            errors = agent_registry.load_errors
            # Pre-warm all registered agents
            for spec in agent_registry:
                try:
                    self._agents[spec.agent_id] = self._build_unified(spec.agent_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to build agent %s: %s", spec.agent_id, exc
                    )
                    errors.append(
                        {"agent_id": spec.agent_id, "error": str(exc)[:200]}
                    )
        return {
            "loaded": loaded,
            "errors": errors,
            "agents": list(self._agents.keys()),
        }

    def list_agents(self) -> Dict[str, Dict[str, Any]]:
        """Return metadata for every registered agent."""
        result = {}
        for spec in agent_registry:
            result[spec.agent_id] = {
                "display_name": spec.display_name,
                "description": spec.description,
                "has_llm": spec.llm_class is not None,
                "slo_p95_latency_ms": spec.slo_p95_latency_ms,
                "slo_min_success_rate": spec.slo_min_success_rate,
                "state_keys": spec.state_keys,
            }
        return result

    def _build_unified(self, name: str) -> UnifiedAgent:
        """Build a UnifiedAgent from registry spec."""
        spec = agent_registry.get(name)
        if spec is None:
            raise ValueError(
                f"Unknown agent: '{name}'. "
                f"Available: {list(agent_registry.specs.keys())}"
            )
        return _build_from_spec(spec)


def _build_from_spec(spec: AgentSpec) -> UnifiedAgent:
    """Construct a UnifiedAgent from an AgentSpec."""
    llm_agent = spec.instantiate_llm()
    rule_agent = spec.instantiate_rule()
    input_adapter = spec.resolve_callable(spec.input_adapter)
    output_adapter = spec.resolve_callable(spec.output_adapter)

    return UnifiedAgent(
        name=spec.agent_id,
        llm_agent=llm_agent,
        rule_agent=rule_agent,
        llm_method=spec.llm_method,
        rule_method=spec.rule_method,
        input_adapter=input_adapter,
        output_adapter=output_adapter,
    )


class UnifiedAgent:
    """Wraps an LLM agent and a rule-based agent into a single interface.

    Tries LLM first, falls back to rule-based on failure.  Emits
    per-agent metrics via ``agent_metrics`` on every execution.
    """

    def __init__(
        self,
        name: str,
        llm_agent: Optional[Any],
        rule_agent: Any,
        llm_method: Optional[str],
        rule_method: str,
        input_adapter: Optional[Any],
        output_adapter: Optional[Any],
    ):
        self.name = name
        self.llm_agent = llm_agent
        self.rule_agent = rule_agent
        self.llm_method = llm_method
        self.rule_method = rule_method
        self.input_adapter = input_adapter
        self.output_adapter = output_adapter

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the agent with LLM-first, rule-based fallback."""
        start = time.monotonic()
        fallback_used = False
        tokens_in = 0
        tokens_out = 0
        cost_usd = 0.0
        decision_type: Optional[str] = None
        confidence: Optional[float] = None
        success = True
        error_msg: Optional[str] = None

        # Try LLM agent if available
        if self.llm_agent and self.llm_method:
            try:
                llm_input = self.input_adapter(state) if self.input_adapter else state
                if llm_input is not None:
                    llm_method = getattr(self.llm_agent, self.llm_method)
                    llm_result = await llm_method(llm_input)

                    # Extract token/cost from LLM response
                    from ecommerce_ops.agents.cost_tracker import track_llm_cost

                    cost_data = track_llm_cost(
                        llm_result, agent=self.name, model="gemini-2.0-flash"
                    )
                    tokens_in = cost_data.get("tokens_input", 0)
                    tokens_out = cost_data.get("tokens_output", 0)
                    cost_usd = cost_data.get("cost_usd", 0.0)

                    adapted = (
                        self.output_adapter(llm_result) if self.output_adapter else None
                    )

                    if adapted:
                        decision = self.rule_agent.create_decision(
                            action_type=adapted["action_type"],
                            reasoning=adapted["reasoning"],
                            data=adapted.get("data", {}),
                            confidence=adapted.get("confidence", 0.5),
                            requires_approval=adapted.get("requires_approval", True),
                        )
                        decisions = [*state.get("decisions", []), decision]
                        state["decisions"] = decisions
                        decision_type = adapted.get("action_type")
                        confidence = adapted.get("confidence")
                        elapsed = (time.monotonic() - start) * 1000
                        logger.info(
                            "Agent %s (LLM) completed in %.1fms",
                            self.name,
                            elapsed,
                        )
                        return state

            except Exception as e:
                fallback_used = True
                error_msg = str(e)[:200]
                logger.warning(
                    "Agent %s LLM failed (%s), falling back to rule-based",
                    self.name,
                    error_msg,
                )

        # Fallback: rule-based agent
        try:
            result = await getattr(self.rule_agent, self.rule_method)(state)
            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                "Agent %s (rule-based) completed in %.1fms",
                self.name,
                elapsed,
            )
            return result
        except Exception as e:
            success = False
            error_msg = str(e)[:200]
            logger.exception("Agent %s rule-based also failed: %s", self.name, e)
            errors = state.get("errors", [])
            errors.append({"agent": self.name, "error": error_msg})
            state["errors"] = errors
            return state
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            agent_metrics.record(
                AgentExecutionRecord(
                    agent=self.name,
                    started_at=start,
                    finished_at=time.monotonic(),
                    latency_ms=elapsed_ms,
                    success=success,
                    fallback_used=fallback_used,
                    tokens_input=tokens_in,
                    tokens_output=tokens_out,
                    cost_usd=cost_usd,
                    error=error_msg,
                    decision_type=decision_type,
                    confidence=confidence,
                )
            )


# Singleton — backward-compatible with existing imports
agent_factory = AgentFactory()
