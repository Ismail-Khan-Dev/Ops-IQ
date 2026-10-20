import logging
from typing import Any, Dict, List

from langgraph.graph import END, StateGraph

from ecommerce_ops.agents.factory import agent_factory
from ecommerce_ops.agents.reflection import ReflectionAgent
from ecommerce_ops.graph.state import ExecutionPlan, OverallState

logger = logging.getLogger("ecommerce_ops.graph.supervisor")

DEFAULT_PLAN = ["fraud", "inventory", "pricing", "reviews", "marketing"]

ALL_KNOWN_AGENTS = [
    "fraud",
    "inventory",
    "pricing",
    "dynamic_pricing",
    "order_swaps",
    "smart_returns",
    "reviews",
    "marketing",
    "cart_recovery",
    "customer_support",
]


def _get_registered_agents() -> List[str]:
    """Retrieve all registered agent IDs from AgentRegistry and fallback list."""
    try:
        from ecommerce_ops.agents.registry import agent_registry

        if len(agent_registry) == 0:
            agent_registry.scan()
        specs = list(agent_registry.specs.keys())
        return list(dict.fromkeys(ALL_KNOWN_AGENTS + specs))
    except Exception:
        return list(ALL_KNOWN_AGENTS)


async def planner(state: Dict[str, Any]) -> Dict[str, Any]:
    plan = []
    if state.get("active_orders"):
        plan.append("fraud")
    if state.get("out_of_stock_items"):
        plan.append("order_swaps")
    if state.get("pending_orders"):
        plan.append("smart_returns")
    if state.get("inventory_data"):
        plan.append("inventory")
        plan.append("pricing")
    if state.get("reviews_data"):
        plan.append("reviews")
    if state.get("abandoned_carts"):
        plan.append("cart_recovery")
    if state.get("support_tickets"):
        plan.append("customer_support")
    if plan:
        plan.append("marketing")

    if not plan:
        plan = list(DEFAULT_PLAN)

    state["execution_plan"] = ExecutionPlan(agents_to_run=plan, rationale="dynamic")
    state["step_index"] = 0
    logger.info("Execution plan: %s", plan)
    return state


async def run_agent(node_name: str, state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        agent = agent_factory.get_agent(node_name)
        result = await agent.run(state)
        idx = state.get("step_index", 0)
        result["step_index"] = idx + 1
        return result
    except Exception as e:
        logger.exception("Agent %s failed: %s", node_name, e)
        errors = state.get("errors", [])
        errors.append({"agent": node_name, "error": str(e)})
        state["errors"] = errors
        state["step_index"] = state.get("step_index", 0) + 1
        return state


def _entry_router(state: Dict[str, Any]) -> str:
    plan: ExecutionPlan = state.get("execution_plan")
    if plan and plan.agents_to_run:
        first_agent = plan.agents_to_run[0]
        registered = _get_registered_agents()
        return first_agent if first_agent in registered else "reflection"
    return "reflection"


async def router(state: Dict[str, Any]) -> str:
    plan: ExecutionPlan = state.get("execution_plan")
    if plan is None:
        return END
    idx = state.get("step_index", 0)
    if idx >= len(plan.agents_to_run):
        return "reflection"
    next_agent = plan.agents_to_run[idx]
    registered = _get_registered_agents()
    return next_agent if next_agent in registered else "reflection"


async def reflection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    decisions = state.get("decisions", [])
    if not decisions:
        return state

    reflection = ReflectionAgent()
    feedback = await reflection.run(decisions)

    corrected = []
    for d, fb in zip(decisions, feedback, strict=False):
        c = await reflection.correct_decision(d, fb)
        corrected.append(c)

    state["decisions"] = corrected
    state["reflection_feedback"] = state.get("reflection_feedback", []) + feedback

    passed = sum(1 for fb in feedback if fb.passed)
    logger.info("Reflection: %d/%d decisions passed validation", passed, len(feedback))
    return state


class Supervisor:
    _compiled_graph = None

    def __init__(self):
        if Supervisor._compiled_graph is None:
            builder = StateGraph(OverallState)
            self._setup_graph(builder)
            Supervisor._compiled_graph = builder.compile()
        self.graph = Supervisor._compiled_graph

    def _setup_graph(self, builder):
        builder.add_node("planner", planner)
        builder.add_node("reflection", reflection_node)

        registered_agents = _get_registered_agents()
        for name in registered_agents:

            async def make_node(state, n=name):
                return await run_agent(n, state)

            builder.add_node(name, make_node)

        all_nodes = [*registered_agents, "reflection", END]
        builder.set_conditional_entry_point(
            lambda s: "planner" if s.get("execution_plan") is None else _entry_router(s),
            {"planner": "planner", **{n: n for n in all_nodes}},
        )

        builder.add_conditional_edges(
            "planner",
            _entry_router,
            {n: n for n in all_nodes},
        )

        for name in registered_agents:
            builder.add_conditional_edges(
                name,
                router,
                {n: n for n in all_nodes},
            )

        builder.add_edge("reflection", END)

    async def run(self, input_state: Dict[str, Any]) -> Dict[str, Any]:
        if "memory_context" not in input_state:
            input_state["memory_context"] = {}
        if "reflection_feedback" not in input_state:
            input_state["reflection_feedback"] = []
        if "step_index" not in input_state:
            input_state["step_index"] = 0
        return await self.graph.ainvoke(input_state)
