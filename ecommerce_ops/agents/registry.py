"""Dynamic agent registry.

Scans ``ecommerce_ops/agents/*/agent.yaml`` at startup and builds a
lookup table of ``AgentSpec`` objects.  The ``AgentFactory`` consumes
this registry instead of hard-coding agent creation.

Adding a new agent = drop a YAML + Python class.  Zero config changes.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("ecommerce_ops.agents.registry")

_AGENTS_DIR = Path(__file__).resolve().parent
_SPECS_DIR = _AGENTS_DIR / "specs"


# ── AgentSpec ──────────────────────────────────────────────


class AgentSpec(BaseModel):
    """Declarative specification for one agent, loaded from YAML."""

    agent_id: str = Field(..., description="Unique registry key, e.g. 'fraud'")
    display_name: str = ""
    description: str = ""

    # LLM variant (optional — rule-only agents omit these)
    llm_class: Optional[str] = None  # dotted import path
    llm_method: Optional[str] = None  # method name on the LLM class

    # Rule-based variant (always required)
    rule_class: str  # dotted import path
    rule_method: str = "run"  # method name on the rule class

    # Input/output adapters (optional — only needed for LLM-first agents)
    input_adapter: Optional[str] = None  # dotted import path to callable
    output_adapter: Optional[str] = None  # dotted import path to callable

    # SLO thresholds
    slo_p95_latency_ms: float = 10000.0
    slo_min_success_rate: float = 0.90

    # Routing: which state keys trigger this agent
    state_keys: List[str] = Field(default_factory=list)

    def resolve_class(self, dotted_path: str) -> Any:
        """Import and return the object at *dotted_path*."""
        module_path, _, attr_name = dotted_path.rpartition(".")
        mod = importlib.import_module(module_path)
        return getattr(mod, attr_name)

    def resolve_callable(self, dotted_path: Optional[str]) -> Optional[Callable[..., Any]]:
        """Resolve a dotted import path to a callable, or None."""
        if not dotted_path:
            return None
        obj = self.resolve_class(dotted_path)
        if not callable(obj):
            raise TypeError(f"{dotted_path} is not callable")
        return obj

    def instantiate_llm(self) -> Optional[Any]:
        """Import and instantiate the LLM agent class (or None)."""
        if not self.llm_class:
            return None
        cls = self.resolve_class(self.llm_class)
        return cls()

    def instantiate_rule(self) -> Any:
        """Import and instantiate the rule-based agent class."""
        cls = self.resolve_class(self.rule_class)
        return cls()


# ── Registry ───────────────────────────────────────────────


class AgentRegistry:
    """Scans agent directories for ``agent.yaml`` files and registers specs."""

    def __init__(self) -> None:
        self._specs: Dict[str, AgentSpec] = {}
        self._load_errors: List[Dict[str, str]] = []

    @property
    def specs(self) -> Dict[str, AgentSpec]:
        return dict(self._specs)

    @property
    def load_errors(self) -> List[Dict[str, str]]:
        return list(self._load_errors)

    def scan(self, base_dir: Optional[Path] = None) -> None:
        """Walk *base_dir* (default: ``agents/specs/``) looking for ``agent.yaml``."""
        specs_dir = base_dir or _SPECS_DIR
        if not specs_dir.is_dir():
            logger.warning("Specs directory not found: %s", specs_dir)
            return
        self._specs.clear()
        self._load_errors.clear()

        for spec_path in sorted(specs_dir.rglob("agent.yaml")):
            try:
                self._load_spec(spec_path)
            except Exception as exc:
                self._load_errors.append(
                    {"path": str(spec_path), "error": str(exc)[:200]}
                )
                logger.warning("Failed to load agent spec %s: %s", spec_path, exc)

        logger.info(
            "Agent registry loaded %d spec(s), %d error(s)",
            len(self._specs),
            len(self._load_errors),
        )

    def _load_spec(self, path: Path) -> None:
        """Parse one YAML file and register the spec."""
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not raw or not isinstance(raw, dict):
            raise ValueError(f"Empty or invalid YAML: {path}")

        spec = AgentSpec(**raw)

        if spec.agent_id in self._specs:
            raise ValueError(
                f"Duplicate agent_id '{spec.agent_id}' in {path} "
                f"(already registered from another spec)"
            )

        self._specs[spec.agent_id] = spec
        logger.debug("Registered agent spec: %s from %s", spec.agent_id, path)

    def get(self, agent_id: str) -> Optional[AgentSpec]:
        return self._specs.get(agent_id)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self):
        return iter(self._specs.values())


# Singleton
agent_registry = AgentRegistry()
