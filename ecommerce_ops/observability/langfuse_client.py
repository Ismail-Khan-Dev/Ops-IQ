"""
Langfuse Client Wrapper
Production-grade Langfuse integration for tracing and evaluation.
"""

import logging
import os
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("ecommerce_ops.observability.langfuse")


class LangfuseConfig(BaseModel):
    """Langfuse configuration."""

    public_key: Optional[str] = None
    secret_key: Optional[str] = None
    host: str = "https://cloud.langfuse.com"
    enabled: bool = True
    flush_interval: int = 1
    max_retries: int = 3
    timeout: int = 10

    @classmethod
    def from_env(cls) -> "LangfuseConfig":
        """Load config from environment variables."""
        return cls(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            enabled=os.getenv("LANGFUSE_ENABLED", "true").lower() == "true",
        )


class TraceContext(BaseModel):
    """Context for a trace."""

    trace_id: str
    name: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LangfuseClient:
    """Wrapper around Langfuse client with fallback handling."""

    def __init__(self, config: Optional[LangfuseConfig] = None):
        self.config = config or LangfuseConfig.from_env()
        self._client = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Ensure Langfuse client is initialized."""
        if self._initialized:
            return self._client is not None

        self._initialized = True

        if not self.config.enabled:
            logger.debug("Langfuse disabled via config")
            return False

        if not self.config.public_key or not self.config.secret_key:
            logger.warning("Langfuse credentials not configured, tracing disabled")
            return False

        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=self.config.public_key,
                secret_key=self.config.secret_key,
                host=self.config.host,
                flush_interval=self.config.flush_interval,
                max_retries=self.config.max_retries,
                timeout=self.config.timeout,
            )
            logger.info("Langfuse client initialized successfully")
            return True

        except ImportError:
            logger.warning("langfuse package not installed, tracing disabled")
            return False
        except Exception as e:
            logger.error("Failed to initialize Langfuse: %s", e)
            return False

    def create_trace(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """Create a new trace."""
        if not self._ensure_initialized():
            return None

        try:
            trace = self._client.trace(
                name=name,
                user_id=user_id,
                session_id=session_id,
                tags=tags or [],
                metadata=metadata or {},
            )
            logger.debug("Created trace: %s", trace.id)
            return trace
        except Exception as e:
            logger.error("Failed to create trace: %s", e)
            return None

    def create_generation(
        self,
        trace_id: str,
        name: str,
        model: str,
        input: Any,
        output: Any,
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: str = "DEFAULT",
    ) -> Optional[Any]:
        """Create a generation (LLM call) within a trace."""
        if not self._ensure_initialized():
            return None

        try:
            generation = self._client.generation(
                trace_id=trace_id,
                name=name,
                model=model,
                input=input,
                output=output,
                usage=usage,
                metadata=metadata or {},
                level=level,
            )
            logger.debug("Created generation: %s", generation.id)
            return generation
        except Exception as e:
            logger.error("Failed to create generation: %s", e)
            return None

    def create_span(
        self,
        trace_id: str,
        name: str,
        input: Any = None,
        output: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: str = "DEFAULT",
    ) -> Optional[Any]:
        """Create a span within a trace."""
        if not self._ensure_initialized():
            return None

        try:
            span = self._client.span(
                trace_id=trace_id,
                name=name,
                input=input,
                output=output,
                metadata=metadata or {},
                level=level,
            )
            logger.debug("Created span: %s", span.id)
            return span
        except Exception as e:
            logger.error("Failed to create span: %s", e)
            return None

    def score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: Optional[str] = None,
    ) -> Optional[Any]:
        """Add a score to a trace."""
        if not self._ensure_initialized():
            return None

        try:
            score = self._client.score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=comment,
            )
            logger.debug("Added score: %s = %.2f", name, value)
            return score
        except Exception as e:
            logger.error("Failed to add score: %s", e)
            return None

    def flush(self):
        """Flush pending events."""
        if self._client:
            try:
                self._client.flush()
            except Exception as e:
                logger.error("Failed to flush Langfuse: %s", e)

    def shutdown(self):
        """Shutdown the client."""
        if self._client:
            try:
                self._client.flush()
                logger.info("Langfuse client shut down")
            except Exception as e:
                logger.error("Failed to shutdown Langfuse: %s", e)

    def get_trace_url(self, trace_id: str) -> str:
        """Get URL for viewing trace in Langfuse dashboard."""
        return f"{self.config.host}/trace/{trace_id}"

    @property
    def is_enabled(self) -> bool:
        """Check if Langfuse is enabled and configured."""
        return self._ensure_initialized()


# Singleton
langfuse_client = LangfuseClient()
