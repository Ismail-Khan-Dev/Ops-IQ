"""
Klaviyo Event Bridge Connector
Provides integration with Klaviyo's modern JSON:API (Revision 2024-02-15).
Enables abandoned cart recovery flows, customer re-engagement, and VIP retention.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.infra.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.connectors.klaviyo")

KLAVIYO_API_URL = "https://a.klaviyo.com/api"
KLAVIYO_API_REVISION = "2024-02-15"


class KlaviyoAPIError(Exception):
    """Raised when Klaviyo returns an error response."""

    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class KlaviyoClient:
    """Async client for Klaviyo JSON:API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = KLAVIYO_API_URL,
        revision: str = KLAVIYO_API_REVISION,
        timeout: float = 15.0,
    ):
        if not api_key and app_settings.KLAVIYO_API_KEY:
            api_key = app_settings.KLAVIYO_API_KEY.get_secret_value()

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.revision = revision
        self.timeout = timeout
        self._circuit_breaker = CircuitBreaker(name="klaviyo", failure_threshold=5, recovery_timeout=30.0)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "revision": self.revision,
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        }
        if self.api_key:
            headers["Authorization"] = f"Klaviyo-API-Key {self.api_key}"
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute HTTP request with circuit breaker and rate limit retry."""
        if not self.is_configured:
            logger.warning("Klaviyo requested without active API key; simulating success in dev")
            return {"simulated": True, "path": path}

        url = f"{self.base_url}{path}"
        headers = self._get_headers()
        client = await self._get_client()

        for attempt in range(3):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params,
                )

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 1.0))
                    logger.warning("Klaviyo rate limit hit; waiting %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code in (200, 201, 202):
                    self._circuit_breaker.record_success()
                    return response.json() if response.content else {}

                self._circuit_breaker.record_failure()
                error_body = response.json() if response.content else {}
                raise KlaviyoAPIError(
                    f"Klaviyo HTTP {response.status_code}: {response.text}",
                    status_code=response.status_code,
                    details=error_body,
                )

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                self._circuit_breaker.record_failure()
                if attempt == 2:
                    raise KlaviyoAPIError(f"Klaviyo network failure: {exc}")
                await asyncio.sleep(0.5 * (attempt + 1))

        return {}

    async def track_event(
        self,
        metric_name: str,
        customer_email: str,
        properties: Dict[str, Any],
        customer_phone: Optional[str] = None,
        event_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Track custom event in Klaviyo to trigger retention & recovery flows.

        Uses modern Klaviyo JSON:API POST /api/events/.
        """
        if not event_time:
            event_time = utc_now().isoformat()

        profile_attrs: Dict[str, Any] = {"email": customer_email}
        if customer_phone:
            profile_attrs["phone_number"] = customer_phone

        payload = {
            "data": {
                "type": "event",
                "attributes": {
                    "metric": {
                        "data": {
                            "type": "metric",
                            "attributes": {
                                "name": metric_name,
                            },
                        }
                    },
                    "profile": {
                        "data": {
                            "type": "profile",
                            "attributes": profile_attrs,
                        }
                    },
                    "properties": properties,
                    "time": event_time,
                },
            }
        }

        try:
            return await self._circuit_breaker.call(
                self._request, "POST", "/events/", json_data=payload
            )
        except CircuitBreakerOpenError:
            logger.error("Klaviyo circuit breaker open; dropping event %s", metric_name)
            return {"error": "circuit_breaker_open"}

    async def trigger_cart_recovery(
        self,
        customer_email: str,
        cart_id: str,
        cart_total: float,
        discount_code: Optional[str] = None,
        discount_value: Optional[float] = None,
        checkout_url: Optional[str] = None,
        recovery_strategy: str = "discount_urgency",
        items_count: int = 1,
    ) -> Dict[str, Any]:
        """Convenience method to trigger 'OpsIQ Cart Recovery Triggered' in Klaviyo."""
        properties = {
            "cart_id": str(cart_id),
            "cart_total": float(cart_total),
            "discount_code": discount_code or "NONE",
            "discount_value": discount_value or 0.0,
            "checkout_url": checkout_url or "",
            "recovery_strategy": recovery_strategy,
            "items_count": items_count,
            "source": "OpsIQ-AbandonedCartAgent",
        }
        return await self.track_event(
            metric_name="OpsIQ Cart Recovery Triggered",
            customer_email=customer_email,
            properties=properties,
        )

    async def close(self):
        """Close underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
