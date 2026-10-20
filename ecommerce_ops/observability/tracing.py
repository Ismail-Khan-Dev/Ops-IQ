"""
Tracing Decorators
Decorators for automatic tracing of agent operations.
"""

import functools
import logging
import time
import uuid
from typing import Any, Callable, Dict, Optional, TypeVar

from ecommerce_ops.observability.langfuse_client import langfuse_client

logger = logging.getLogger("ecommerce_ops.observability.tracing")

F = TypeVar("F", bound=Callable[..., Any])


def trace_agent(
    agent_name: str,
    tags: Optional[list[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Callable[[F], F]:
    """Decorator to trace agent execution."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            trace_id = str(uuid.uuid4())
            start_time = time.time()

            # Create trace
            trace = langfuse_client.create_trace(
                name=f"agent.{agent_name}.{func.__name__}",
                user_id=kwargs.get("user_id"),
                session_id=kwargs.get("session_id"),
                tags=tags or [agent_name],
                metadata={
                    **(metadata or {}),
                    "agent": agent_name,
                    "function": func.__name__,
                },
            )

            try:
                # Execute the function
                result = await func(*args, **kwargs)

                # Add success score
                if trace:
                    langfuse_client.score(
                        trace_id=trace_id,
                        name="success",
                        value=1.0,
                        comment="Agent executed successfully",
                    )

                # Track metrics
                duration = time.time() - start_time
                if trace and result:
                    langfuse_client.create_span(
                        trace_id=trace_id,
                        name="result_summary",
                        input={"agent": agent_name},
                        output={
                            "decisions_count": len(result.get("decisions", [])),
                            "duration_ms": round(duration * 1000, 2),
                        },
                    )

                logger.debug(
                    "Agent %s completed in %.2fms",
                    agent_name,
                    duration * 1000,
                )

                return result

            except Exception as e:
                # Add failure score
                if trace:
                    langfuse_client.score(
                        trace_id=trace_id,
                        name="success",
                        value=0.0,
                        comment=f"Agent failed: {e!s}",
                    )

                logger.error("Agent %s failed: %s", agent_name, e)
                raise

        return wrapper  # type: ignore

    return decorator


def trace_llm_call(
    model: str,
    name: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Callable[[F], F]:
    """Decorator to trace LLM calls."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            call_name = name or func.__name__
            start_time = time.time()

            # Get or create trace context
            trace_id = kwargs.pop("trace_id", None)

            try:
                # Execute the LLM call
                result = await func(*args, **kwargs)

                # Track generation
                if trace_id:
                    duration = time.time() - start_time
                    usage = _extract_usage(result) or kwargs.get("usage")
                    langfuse_client.create_generation(
                        trace_id=trace_id,
                        name=call_name,
                        model=model,
                        input=kwargs.get("prompt", kwargs.get("messages", "")),
                        output=result,
                        usage=usage,
                        metadata={
                            "duration_ms": round(duration * 1000, 2),
                            "function": func.__name__,
                        },
                    )

                return result

            except Exception as e:
                logger.error("LLM call %s failed: %s", call_name, e)
                raise

        return wrapper  # type: ignore

    return decorator


def _extract_usage(result: Any) -> Optional[Dict[str, Any]]:
    """Best-effort extraction of token usage from an LLM response.

    Prefer usage that comes back *in* the model's response (mapping/message
    shapes) rather than expecting the caller to forward it as a keyword arg,
    which is easy to miss and was the source of silent ``usage=None`` spans.
    """
    if isinstance(result, dict):
        usage = result.get("usage")
        if isinstance(usage, dict):
            return usage
        usage_meta = result.get("usage_metadata")
        if isinstance(usage_meta, dict):
            return usage_meta
    usage_attr = getattr(result, "usage", None)
    if usage_attr is None:
        return None
    if isinstance(usage_attr, dict):
        return usage_attr
    try:
        return dict(usage_attr)
    except Exception:
        return None


def trace_tool(
    tool_name: str,
    tags: Optional[list[str]] = None,
) -> Callable[[F], F]:
    """Decorator to trace tool usage."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            trace_id = kwargs.pop("trace_id", None)

            try:
                result = await func(*args, **kwargs)

                # Track tool span
                if trace_id:
                    duration = time.time() - start_time
                    langfuse_client.create_span(
                        trace_id=trace_id,
                        name=f"tool.{tool_name}",
                        input=kwargs,
                        output=result,
                        metadata={
                            "duration_ms": round(duration * 1000, 2),
                            "success": True,
                        },
                    )

                return result

            except Exception as e:
                # Track failed tool
                if trace_id:
                    langfuse_client.create_span(
                        trace_id=trace_id,
                        name=f"tool.{tool_name}",
                        input=kwargs,
                        output={"error": str(e)},
                        metadata={"success": False},
                        level="ERROR",
                    )

                logger.error("Tool %s failed: %s", tool_name, e)
                raise

        return wrapper  # type: ignore

    return decorator


def trace_pipeline(
    pipeline_name: str,
    tags: Optional[list[str]] = None,
) -> Callable[[F], F]:
    """Decorator to trace pipeline execution."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            trace_id = str(uuid.uuid4())
            start_time = time.time()

            # Create pipeline trace
            trace = langfuse_client.create_trace(
                name=f"pipeline.{pipeline_name}",
                user_id=kwargs.get("user_id"),
                tags=tags or ["pipeline", pipeline_name],
                metadata={
                    "pipeline": pipeline_name,
                    "function": func.__name__,
                },
            )

            try:
                result = await func(*args, **kwargs)

                # Add success score
                if trace:
                    duration = time.time() - start_time
                    langfuse_client.score(
                        trace_id=trace_id,
                        name="pipeline_success",
                        value=1.0,
                        comment=f"Pipeline {pipeline_name} completed in {duration:.2f}s",
                    )

                    # Track result summary
                    langfuse_client.create_span(
                        trace_id=trace_id,
                        name="pipeline_result",
                        output={
                            "duration_ms": round(duration * 1000, 2),
                            "result_keys": list(result.keys()) if isinstance(result, dict) else [],
                        },
                    )

                return result

            except Exception as e:
                if trace:
                    langfuse_client.score(
                        trace_id=trace_id,
                        name="pipeline_success",
                        value=0.0,
                        comment=f"Pipeline failed: {e!s}",
                    )

                logger.error("Pipeline %s failed: %s", pipeline_name, e)
                raise

        return wrapper  # type: ignore

    return decorator


class TracedAgent:
    """Context manager for tracing agent operations."""

    def __init__(
        self,
        agent_name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.agent_name = agent_name
        self.user_id = user_id
        self.session_id = session_id
        self.tags = tags or []
        self.metadata = metadata or {}
        self.trace_id = str(uuid.uuid4())
        self.trace = None
        self.start_time = None

    async def __aenter__(self):
        self.start_time = time.time()
        self.trace = langfuse_client.create_trace(
            name=f"agent.{self.agent_name}",
            user_id=self.user_id,
            session_id=self.session_id,
            tags=[self.agent_name, *self.tags],
            metadata=self.metadata,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type:
            langfuse_client.score(
                trace_id=self.trace_id,
                name="success",
                value=0.0,
                comment=f"Failed: {exc_val!s}",
            )
        else:
            langfuse_client.score(
                trace_id=self.trace_id,
                name="success",
                value=1.0,
                comment=f"Completed in {duration:.2f}s",
            )

        return False

    def add_score(self, name: str, value: float, comment: Optional[str] = None):
        """Add a score to the trace."""
        langfuse_client.score(
            trace_id=self.trace_id,
            name=name,
            value=value,
            comment=comment,
        )

    def add_span(
        self,
        name: str,
        input: Any = None,
        output: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Add a span to the trace."""
        langfuse_client.create_span(
            trace_id=self.trace_id,
            name=name,
            input=input,
            output=output,
            metadata=metadata,
        )
