"""
Tool Executor - Permission-checked tool execution with audit logging.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from ecommerce_ops.tools.definitions import tool_registry

logger = logging.getLogger("ecommerce_ops.tools.executor")


class ToolExecutor:
    """Execute tools with permission checking, retry logic, and audit logging."""

    def __init__(self):
        self.registry = tool_registry
        self._execution_history: List[Dict[str, Any]] = []

    async def execute(
        self,
        tool_name: str,
        agent_id: str,
        arguments: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool with permission checking.

        Returns:
            Dict with keys: success, result, error, execution_time_ms
        """
        start_time = time.time()

        # Permission check
        if not self.registry.has_permission(agent_id, tool_name):
            logger.warning(f"Permission denied: {agent_id} tried to use {tool_name}")
            return {
                "success": False,
                "result": None,
                "error": f"Agent {agent_id} does not have permission to use tool {tool_name}",
                "execution_time_ms": 0,
            }

        # Get tool
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return {
                "success": False,
                "result": None,
                "error": f"Tool {tool_name} not found",
                "execution_time_ms": 0,
            }

        # Execute
        try:
            result = await tool.ainvoke(arguments)
            execution_time = (time.time() - start_time) * 1000

            # Log success
            entry = {
                "tool_name": tool_name,
                "agent_id": agent_id,
                "arguments": arguments,
                "result": result,
                "success": True,
                "execution_time_ms": execution_time,
                "trace_id": trace_id,
            }
            self._execution_history.append(entry)

            logger.info(f"Tool executed: {tool_name} by {agent_id} in {execution_time:.1f}ms")

            return {
                "success": True,
                "result": result,
                "error": None,
                "execution_time_ms": execution_time,
            }

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Tool execution failed: {tool_name} - {e}")

            entry = {
                "tool_name": tool_name,
                "agent_id": agent_id,
                "arguments": arguments,
                "result": None,
                "success": False,
                "error": str(e),
                "execution_time_ms": execution_time,
                "trace_id": trace_id,
            }
            self._execution_history.append(entry)

            return {
                "success": False,
                "result": None,
                "error": str(e),
                "execution_time_ms": execution_time,
            }

    async def execute_batch(
        self,
        tool_calls: List[Dict[str, Any]],
        agent_id: str,
        trace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tool calls.

        Args:
            tool_calls: List of {tool_name, arguments} dicts
        """
        results = []
        for call in tool_calls:
            result = await self.execute(
                tool_name=call["tool_name"],
                agent_id=agent_id,
                arguments=call.get("arguments", {}),
                trace_id=trace_id,
            )
            results.append(result)
        return results

    def get_history(
        self,
        agent_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get execution history with optional filters."""
        history = self._execution_history

        if agent_id:
            history = [h for h in history if h["agent_id"] == agent_id]
        if tool_name:
            history = [h for h in history if h["tool_name"] == tool_name]

        return history[-limit:]

    def get_stats(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get execution statistics."""
        history = self._execution_history
        if agent_id:
            history = [h for h in history if h["agent_id"] == agent_id]

        if not history:
            return {"total_calls": 0, "success_rate": 0, "avg_execution_time_ms": 0}

        successful = [h for h in history if h["success"]]
        execution_times = [h["execution_time_ms"] for h in history]

        return {
            "total_calls": len(history),
            "successful_calls": len(successful),
            "failed_calls": len(history) - len(successful),
            "success_rate": len(successful) / len(history) if history else 0,
            "avg_execution_time_ms": sum(execution_times) / len(execution_times)
            if execution_times
            else 0,
        }


# Singleton
tool_executor = ToolExecutor()
