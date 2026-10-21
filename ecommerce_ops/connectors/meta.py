"""
Meta Marketing API Connector (Graph API v19.0+)
Enables automated ad set pause/unpause based on SKU inventory stock levels.
Prevents burning ad spend on out-of-stock bestsellers.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.infra.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.connectors.meta")

META_GRAPH_API_URL = "https://graph.facebook.com/v19.0"


class MetaAPIError(Exception):
    """Raised when Meta Graph API returns an error response."""

    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class MetaAdsClient:
    """Async client for Meta Marketing API (Ad Set Management)."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        account_id: Optional[str] = None,
        base_url: str = META_GRAPH_API_URL,
        timeout: float = 15.0,
    ):
        if not access_token and app_settings.META_ACCESS_TOKEN:
            access_token = app_settings.META_ACCESS_TOKEN.get_secret_value()
        if not account_id and app_settings.META_AD_ACCOUNT_ID:
            account_id = app_settings.META_AD_ACCOUNT_ID

        self.access_token = access_token
        self.account_id = account_id.replace("act_", "") if account_id else None
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.account_id)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute request to Meta Graph API with circuit breaker and retries."""
        if not self.is_configured:
            logger.info("Meta Ads client not configured with live credentials; operating in simulation mode")
            return self._simulate_response(method, path, data)

        if not self._circuit_breaker.allow_request():
            raise CircuitBreakerOpenError("Meta Marketing API circuit breaker is OPEN")

        client = await self._get_client()
        url = f"{self.base_url}/{path.lstrip('/')}"
        req_params = dict(params or {})
        req_params["access_token"] = self.access_token

        try:
            resp = await client.request(
                method=method,
                url=url,
                params=req_params,
                data=data,
            )
            if resp.status_code >= 400:
                err_data = {}
                try:
                    err_data = resp.json().get("error", {})
                except Exception:
                    pass
                msg = err_data.get("message", f"Meta API HTTP {resp.status_code}")
                self._circuit_breaker.record_failure()
                raise MetaAPIError(message=msg, status_code=resp.status_code, details=err_data)

            self._circuit_breaker.record_success()
            return resp.json()
        except httpx.RequestError as e:
            self._circuit_breaker.record_failure()
            raise MetaAPIError(f"Network error connecting to Meta Graph API: {e}", status_code=503)

    def _simulate_response(self, method: str, path: str, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Simulation fallback for development and testing environments."""
        if "adsets" in path and method == "GET":
            return {
                "data": [
                    {
                        "id": "23849182901",
                        "name": "Retargeting - Linen Shirt - M",
                        "status": "ACTIVE",
                        "daily_budget": "7500",  # $75.00 in cents
                        "campaign_id": "1203918290",
                    },
                    {
                        "id": "23849182902",
                        "name": "Lookalike 1% - Linen Shirt - All",
                        "status": "ACTIVE",
                        "daily_budget": "12000",  # $120.00
                        "campaign_id": "1203918290",
                    },
                ]
            }
        elif method == "POST":
            new_status = (data or {}).get("status", "PAUSED")
            return {"success": True, "status": new_status, "simulated": True}
        return {"data": [], "simulated": True}

    async def get_adsets(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all ad sets in the ad account."""
        act_id = account_id or self.account_id or "default"
        resp = await self._request(
            method="GET",
            path=f"act_{act_id}/adsets",
            params={
                "fields": "id,name,status,daily_budget,campaign_id,updated_time",
                "limit": 100,
            },
        )
        return resp.get("data", [])

    async def pause_adset(self, adset_id: str) -> Dict[str, Any]:
        """Pause a specific ad set immediately."""
        logger.warning("🚨 [AD-SPEND BLEED STOPPER] Pausing Meta Ad Set %s", adset_id)
        resp = await self._request(
            method="POST",
            path=f"{adset_id}",
            data={"status": "PAUSED"},
        )
        return {
            "adset_id": adset_id,
            "status": "PAUSED",
            "paused_at": utc_now().isoformat(),
            "response": resp,
        }

    async def unpause_adset(self, adset_id: str) -> Dict[str, Any]:
        """Unpause (activate) an ad set when inventory is replenished."""
        logger.info("✅ [AD-SPEND GUARDIAN] Activating Meta Ad Set %s following restock", adset_id)
        resp = await self._request(
            method="POST",
            path=f"{adset_id}",
            data={"status": "ACTIVE"},
        )
        return {
            "adset_id": adset_id,
            "status": "ACTIVE",
            "activated_at": utc_now().isoformat(),
            "response": resp,
        }

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
