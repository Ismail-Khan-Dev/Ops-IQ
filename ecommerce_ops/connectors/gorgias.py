"""
Gorgias Helpdesk Bridge Connector
Provides integration with Gorgias REST API for ticket routing,
AI draft response injection, internal agent notes, and priority tagging.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.infra.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger("ecommerce_ops.connectors.gorgias")


class GorgiasAPIError(Exception):
    """Raised when Gorgias returns an error response."""

    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class GorgiasClient:
    """Async client for Gorgias Helpdesk REST API."""

    def __init__(
        self,
        domain: Optional[str] = None,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 15.0,
    ):
        domain = domain or app_settings.GORGIAS_DOMAIN
        email = email or app_settings.GORGIAS_EMAIL
        if not api_key and app_settings.GORGIAS_API_KEY:
            api_key = app_settings.GORGIAS_API_KEY.get_secret_value()

        # Sanitize domain (e.g. "mybrand.gorgias.com" or "mybrand")
        if domain:
            domain = domain.lower().replace("https://", "").replace("http://", "").rstrip("/")
            if not domain.endswith(".gorgias.com"):
                domain = f"{domain}.gorgias.com"

        self.domain = domain
        self.email = email
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = f"https://{domain}/api" if domain else ""
        self._circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.domain and self.email and self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            auth = (self.email, self.api_key) if self.email and self.api_key else None
            self._client = httpx.AsyncClient(auth=auth, timeout=self.timeout)
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute Gorgias HTTP request with circuit breaker and retry."""
        if not self.is_configured:
            logger.warning("Gorgias requested without active credentials; simulating success in dev")
            return {"simulated": True, "path": path}

        url = f"{self.base_url}{path}"
        client = await self._get_client()

        for attempt in range(3):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params,
                )

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 2.0))
                    logger.warning("Gorgias rate limit hit; waiting %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code in (200, 201, 204):
                    self._circuit_breaker.record_success()
                    return response.json() if response.content else {}

                self._circuit_breaker.record_failure()
                error_body = response.json() if response.content else {}
                raise GorgiasAPIError(
                    f"Gorgias HTTP {response.status_code}: {response.text}",
                    status_code=response.status_code,
                    details=error_body,
                )

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                self._circuit_breaker.record_failure()
                if attempt == 2:
                    raise GorgiasAPIError(f"Gorgias network failure: {exc}")
                await asyncio.sleep(0.5 * (attempt + 1))

        return {}

    async def get_ticket(self, ticket_id: int | str) -> Dict[str, Any]:
        """Fetch Gorgias ticket by ID."""
        try:
            return await self._circuit_breaker.call(self._request, "GET", f"/tickets/{ticket_id}")
        except CircuitBreakerOpenError:
            logger.error("Gorgias circuit open for GET ticket %s", ticket_id)
            return {}

    async def add_internal_note(
        self, ticket_id: int | str, note_body: str
    ) -> Dict[str, Any]:
        """Add an internal note to a Gorgias ticket for human support agents."""
        payload = {
            "channel": "internal-note",
            "body_text": note_body,
            "from_agent": True,
        }
        try:
            return await self._circuit_breaker.call(
                self._request, "POST", f"/tickets/{ticket_id}/messages", json_data=payload
            )
        except CircuitBreakerOpenError:
            logger.error("Gorgias circuit open for add_internal_note on %s", ticket_id)
            return {"error": "circuit_breaker_open"}

    async def post_ticket_reply(
        self, ticket_id: int | str, reply_text: str
    ) -> Dict[str, Any]:
        """Post a customer-facing reply message to a Gorgias ticket."""
        payload = {
            "channel": "email",
            "body_text": reply_text,
            "from_agent": True,
        }
        try:
            return await self._circuit_breaker.call(
                self._request, "POST", f"/tickets/{ticket_id}/messages", json_data=payload
            )
        except CircuitBreakerOpenError:
            logger.error("Gorgias circuit open for post_ticket_reply on %s", ticket_id)
            return {"error": "circuit_breaker_open"}

    async def create_ticket(
        self,
        customer_email: str,
        subject: str,
        message_body: str,
        tags: Optional[List[str]] = None,
        customer_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new Gorgias ticket."""
        tag_objs = [{"name": t} for t in (tags or ["opsiq-automated"])]
        payload = {
            "customer": {
                "email": customer_email,
                "name": customer_name or customer_email.split("@")[0],
            },
            "subject": subject,
            "channel": "email",
            "messages": [
                {
                    "channel": "email",
                    "from_agent": False,
                    "via": "api",
                    "subject": subject,
                    "body_text": message_body,
                    "sender": {"email": customer_email},
                }
            ],
            "tags": tag_objs,
        }
        try:
            return await self._circuit_breaker.call(
                self._request, "POST", "/tickets", json_data=payload
            )
        except CircuitBreakerOpenError:
            logger.error("Gorgias circuit open for create_ticket")
            return {"error": "circuit_breaker_open"}

    async def update_ticket_tags(
        self, ticket_id: int | str, tags: List[str]
    ) -> Dict[str, Any]:
        """Add or update tags on a Gorgias ticket."""
        tag_objs = [{"name": t} for t in tags]
        payload = {"tags": tag_objs}
        try:
            return await self._circuit_breaker.call(
                self._request, "PUT", f"/tickets/{ticket_id}", json_data=payload
            )
        except CircuitBreakerOpenError:
            logger.error("Gorgias circuit open for update_ticket_tags on %s", ticket_id)
            return {"error": "circuit_breaker_open"}

    async def close(self):
        """Close underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
