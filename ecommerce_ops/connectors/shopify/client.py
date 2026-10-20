"""
Shopify Async HTTP Client
Production-grade client with rate limiting, retry, and pagination.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from ecommerce_ops.infra.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger("ecommerce_ops.connectors.shopify.client")


class ShopifyRateLimitError(Exception):
    """Raised when Shopify rate limit is hit."""

    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


class ShopifyClient:
    """Async Shopify Admin API client with rate limiting and retry."""

    _circuit_breaker = CircuitBreaker(name="ShopifyAPI", failure_threshold=5, recovery_timeout=60.0)

    def __init__(self, shop_domain: str, access_token: str, api_version: str = "2024-01"):
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f"https://{shop_domain}/admin/api/{api_version}"
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limit_remaining = 40
        self._rate_limit_reset_at = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "X-Shopify-Access-Token": self.access_token,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make authenticated request with rate limit handling."""
        # Check rate limit
        if self._rate_limit_remaining <= 1:
            wait_time = max(0, self._rate_limit_reset_at - time.time())
            if wait_time > 0:
                logger.warning("Rate limit near exhaustion, waiting %.1fs", wait_time)
                await asyncio.sleep(wait_time)

        client = await self._get_client()

        try:
            response = await client.request(method, path, **kwargs)

            # Update rate limit tracking
            self._rate_limit_remaining = int(
                response.headers.get("X-Shopify-Shop-Api-Call-Limit", "40/40").split("/")[0]
            )
            reset_at = response.headers.get("X-RateLimit-Reset")
            if reset_at:
                self._rate_limit_reset_at = float(reset_at)

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "2"))
                raise ShopifyRateLimitError(retry_after)

            response.raise_for_status()
            return response.json()

        except ShopifyRateLimitError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Shopify API error: %s %s -> %s", method, path, e.response.status_code)
            raise
        except Exception as e:
            logger.error("Shopify request error: %s %s -> %s", method, path, e)
            raise

    async def _get_with_retry(self, path: str, params: Optional[Dict] = None) -> Dict:
        """GET with automatic retry on rate limit."""
        try:
            return await self._circuit_breaker.call(self._request, "GET", path, params=params)
        except CircuitBreakerOpenError:
            logger.warning("Shopify circuit open for GET %s", path)
            return {}
        except ShopifyRateLimitError as e:
            logger.warning("Rate limited on GET %s, waiting %.1fs", path, e.retry_after)
            await asyncio.sleep(e.retry_after)
            return await self._request("GET", path, params=params)

    async def _post_with_retry(self, path: str, json: Optional[Dict] = None) -> Dict:
        """POST with automatic retry on rate limit."""
        try:
            return await self._circuit_breaker.call(self._request, "POST", path, json=json)
        except CircuitBreakerOpenError:
            logger.warning("Shopify circuit open for POST %s", path)
            return {}
        except ShopifyRateLimitError as e:
            logger.warning("Rate limited on POST %s, waiting %.1fs", path, e.retry_after)
            await asyncio.sleep(e.retry_after)
            return await self._request("POST", path, json=json)

    async def _put_with_retry(self, path: str, json: Optional[Dict] = None) -> Dict:
        """PUT with automatic retry on rate limit."""
        try:
            return await self._circuit_breaker.call(self._request, "PUT", path, json=json)
        except CircuitBreakerOpenError:
            logger.warning("Shopify circuit open for PUT %s", path)
            return {}
        except ShopifyRateLimitError as e:
            logger.warning("Rate limited on PUT %s, waiting %.1fs", path, e.retry_after)
            await asyncio.sleep(e.retry_after)
            return await self._request("PUT", path, json=json)

    # ── Products ────────────────────────────────────────────

    async def get_products(self, limit: int = 50, page_info: Optional[str] = None) -> Dict:
        """Get products with pagination support."""
        params = {"limit": min(limit, 250)}
        if page_info:
            params["page_info"] = page_info
            params.pop("limit", None)  # page_info overrides limit
        return await self._get_with_retry("/products.json", params=params)

    async def get_product(self, product_id: str) -> Dict:
        """Get single product by ID."""
        return await self._get_with_retry(f"/products/{product_id}.json")

    async def update_product(self, product_id: str, product_data: Dict) -> Dict:
        """Update product."""
        return await self._put_with_retry(
            f"/products/{product_id}.json", json={"product": product_data}
        )

    # ── Orders ──────────────────────────────────────────────

    async def get_orders(
        self,
        status: str = "any",
        limit: int = 50,
        page_info: Optional[str] = None,
        created_at_min: Optional[str] = None,
        created_at_max: Optional[str] = None,
    ) -> Dict:
        """Get orders with filters and pagination."""
        params = {"status": status, "limit": min(limit, 250)}
        if page_info:
            params["page_info"] = page_info
            params.pop("limit", None)
        if created_at_min:
            params["created_at_min"] = created_at_min
        if created_at_max:
            params["created_at_max"] = created_at_max
        return await self._get_with_retry("/orders.json", params=params)

    async def get_order(self, order_id: str) -> Dict:
        """Get single order by ID."""
        return await self._get_with_retry(f"/orders/{order_id}.json")

    async def update_order(self, order_id: str, order_data: Dict) -> Dict:
        """Update order."""
        return await self._put_with_retry(f"/orders/{order_id}.json", json={"order": order_data})

    # ── Customers ───────────────────────────────────────────

    async def get_customers(self, limit: int = 50, page_info: Optional[str] = None) -> Dict:
        """Get customers with pagination."""
        params = {"limit": min(limit, 250)}
        if page_info:
            params["page_info"] = page_info
            params.pop("limit", None)
        return await self._get_with_retry("/customers.json", params=params)

    async def get_customer(self, customer_id: str) -> Dict:
        """Get single customer by ID."""
        return await self._get_with_retry(f"/customers/{customer_id}.json")

    # ── Inventory ───────────────────────────────────────────

    async def get_inventory_levels(self, location_id: Optional[str] = None) -> Dict:
        """Get inventory levels."""
        params = {}
        if location_id:
            params["location_ids"] = location_id
        return await self._get_with_retry("/inventory_levels.json", params=params)

    async def adjust_inventory_level(
        self,
        inventory_item_id: str,
        location_id: str,
        available: int,
    ) -> Dict:
        """Adjust inventory level at a location."""
        return await self._post_with_retry(
            "/inventory_levels/adjust.json",
            json={
                "inventory_item_id": inventory_item_id,
                "location_id": location_id,
                "available": available,
            },
        )

    async def set_inventory_level(
        self,
        inventory_item_id: str,
        location_id: str,
        available: int,
    ) -> Dict:
        """Set inventory level at a location."""
        return await self._post_with_retry(
            "/inventory_levels/set.json",
            json={
                "inventory_item_id": inventory_item_id,
                "location_id": location_id,
                "available": available,
            },
        )

    # ── Locations ───────────────────────────────────────────

    async def get_locations(self) -> Dict:
        """Get all locations."""
        return await self._get_with_retry("/locations.json")

    # ── Fulfillments ────────────────────────────────────────

    async def get_order_fulfillments(self, order_id: str) -> Dict:
        """Get fulfillments for an order."""
        return await self._get_with_retry(f"/orders/{order_id}/fulfillments.json")

    async def create_fulfillment(
        self,
        order_id: str,
        line_items: List[Dict],
        tracking_number: Optional[str] = None,
        tracking_company: Optional[str] = None,
    ) -> Dict:
        """Create fulfillment for an order."""
        fulfillment_data = {
            "line_items": line_items,
            "notify_customer": True,
        }
        if tracking_number:
            fulfillment_data["tracking_number"] = tracking_number
        if tracking_company:
            fulfillment_data["tracking_company"] = tracking_company

        return await self._post_with_retry(
            f"/orders/{order_id}/fulfillments.json",
            json={"fulfillment": fulfillment_data},
        )

    # ── Checkouts (Abandoned Cart) ──────────────────────────

    async def get_checkouts(self, limit: int = 50) -> Dict:
        """Get checkouts (abandoned carts)."""
        return await self._get_with_retry("/checkouts.json", params={"limit": min(limit, 250)})

    # ── Discounts / Price Rules (marketing_campaign) ────────

    async def create_price_rule(self, rule: Dict) -> Dict:
        """Create a Shopify price rule (campaign discount).

        ``rule`` maps directly to the Admin API body, e.g.
        ``{"title": ..., "value_type": "percentage", "value": "-15.0",
           "target_type": "line_item", "target_selection": "all"}``.
        """
        return await self._post_with_retry("/price_rules.json", json={"price_rule": rule})

    async def create_discount_code(self, price_rule_id: str, code: str) -> Dict:
        """Attach a discount code to an existing price rule."""
        return await self._post_with_retry(
            f"/price_rules/{price_rule_id}/discount_codes.json",
            json={"discount_code": {"code": code}},
        )

    # ── Product Reviews (review_response) ───────────────────
    # Requires the Shopify Product Reviews API scope
    # (``read_product_reviews`` / ``write_product_reviews``). If the shop has
    # not installed/approved the reviews app, Shopify returns 403/404 and the
    # call is reported as an honest capability failure by the executor.

    async def get_product_reviews(self, limit: int = 50) -> Dict:
        """List product reviews (requires reviews API scope)."""
        return await self._get_with_retry("/product_reviews.json", params={"limit": min(limit, 50)})

    async def post_review_reply(self, review_id: str, reply: str) -> Dict:
        """Post a reply to a product review (requires reviews API scope)."""
        return await self._post_with_retry(
            f"/product_reviews/{review_id}/replies.json",
            json={"product_review_reply": {"reply": reply, "status": "published"}},
        )

    # ── Shop Info ───────────────────────────────────────────

    async def get_shop_info(self) -> Dict:
        """Get shop information."""
        return await self._get_with_retry("/shop.json")

    # ── Close Client ────────────────────────────────────────

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
