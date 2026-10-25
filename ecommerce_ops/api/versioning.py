"""API versioning middleware and router setup.

Provides /api/v1/ prefix with deprecation headers for legacy /api/ routes.
"""

import logging

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("ecommerce_ops.api.versioning")


class APIVersionMiddleware(BaseHTTPMiddleware):
    """Adds API version headers and deprecation warnings to legacy routes."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        path = request.url.path

        if path.startswith("/api/") and not path.startswith("/api/v1"):
            response.headers["X-API-Version"] = "deprecated"
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = "2026-12-31"
            response.headers["Link"] = "</api/v1" + path[4:] + '>; rel="successor-version"'

        if path.startswith("/api/v1"):
            response.headers["X-API-Version"] = "1.0"

        return response


def create_v1_router(
    shopify_router,
    cart_recovery_router,
    customer_support_router,
    observability_router,
    memory_router,
    security_router,
    demo_router,
    core_router=None,
    integrations_router=None,
    slack_router=None,
    roi_router=None,
    onboarding_router=None,
    marketing_router=None,
) -> APIRouter:
    """Create a versioned API router with all v1 endpoints.

    Returns a router that mounts at /api/v1/ and includes all existing routers.
    Legacy /api/ routes remain for backward compatibility but include deprecation headers.
    """
    v1 = APIRouter(prefix="/api/v1")

    v1.include_router(shopify_router, tags=["v1"])
    v1.include_router(cart_recovery_router, tags=["v1"])
    v1.include_router(customer_support_router, tags=["v1"])
    v1.include_router(observability_router, tags=["v1"])
    v1.include_router(memory_router, tags=["v1"])
    v1.include_router(security_router, tags=["v1"])
    v1.include_router(demo_router, tags=["v1"])
    if integrations_router is not None:
        v1.include_router(integrations_router, tags=["v1"])
    if slack_router is not None:
        v1.include_router(slack_router, tags=["v1"])
    if roi_router is not None:
        v1.include_router(roi_router, tags=["v1"])
    if onboarding_router is not None:
        v1.include_router(onboarding_router, tags=["v1"])
    if marketing_router is not None:
        v1.include_router(marketing_router, tags=["v1"])
    if core_router is not None:
        v1.include_router(core_router, tags=["v1"])

    @v1.get("/version", tags=["v1"])
    async def api_version():
        return {
            "version": "1.0",
            "status": "current",
            "sunset_date": "2026-12-31",
            "changelog": "https://github.com/Ismail-2001/ecom-ops-automation-system/blob/main/CHANGELOG.md",
        }

    logger.info("API v1 router created with %d routes", len(v1.routes))
    return v1
