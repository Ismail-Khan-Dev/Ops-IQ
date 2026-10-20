"""Tests for api/metrics.py, api/versioning.py, and api/demo.py."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ecommerce_ops.api.metrics import (
    METRIC_AGENT_CONFIDENCE_AVG,
    METRIC_DECISIONS_CREATED,
    METRIC_HTTP_DURATION,
    METRIC_HTTP_REQUESTS,
    METRIC_PIPELINE_RUNS,
)
from ecommerce_ops.api.versioning import APIVersionMiddleware, create_v1_router


def _flatten_route_paths(router) -> list:
    """Resolve a FastAPI router's full route paths.

    FastAPI >= 0.115 mounts included routers as lazy ``_IncludedRouter``
    wrappers that expose no ``path`` attribute; resolve those to the routes of
    their underlying router so assertions stay version-agnostic.
    """
    paths = []
    for route in router.routes:
        if hasattr(route, "path"):
            paths.append(route.path)
        else:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                paths.extend(getattr(r, "path", "") for r in inner.routes if hasattr(r, "path"))
    return paths

# ── metrics.py tests ───────────────────────────────────────


class TestMetrics:
    def test_metric_http_requests_exists(self):
        assert METRIC_HTTP_REQUESTS is not None

    def test_metric_http_duration_exists(self):
        assert METRIC_HTTP_DURATION is not None

    def test_metric_pipeline_runs_exists(self):
        assert METRIC_PIPELINE_RUNS is not None

    def test_metric_decisions_created_exists(self):
        assert METRIC_DECISIONS_CREATED is not None

    def test_metric_agent_confidence_exists(self):
        assert METRIC_AGENT_CONFIDENCE_AVG is not None

    def test_metrics_can_be_incremented(self):
        from prometheus_client import Counter
        c = Counter("test_counter_increment", "test")
        c.inc()
        assert c._value.get() == 1


# ── versioning.py tests ────────────────────────────────────


class TestAPIVersionMiddleware:
    def setup_method(self):
        self.app = FastAPI()
        self.app.add_middleware(APIVersionMiddleware)

        @self.app.get("/api/test")
        async def test_route():
            return {"ok": True}

        @self.app.get("/api/v1/test")
        async def v1_route():
            return {"ok": True}

        self.client = TestClient(self.app)

    def test_legacy_route_has_deprecation_headers(self):
        resp = self.client.get("/api/test")
        assert resp.status_code == 200
        assert resp.headers.get("x-api-version") == "deprecated"
        assert resp.headers.get("deprecation") == "true"
        assert "sunset" in resp.headers
        assert "link" in resp.headers

    def test_v1_route_has_version_header(self):
        resp = self.client.get("/api/v1/test")
        assert resp.status_code == 200
        assert resp.headers.get("x-api-version") == "1.0"

    def test_non_api_route_no_version_header(self):
        @self.app.get("/health")
        async def health():
            return {"ok": True}

        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert "x-api-version" not in resp.headers


class TestCreateV1Router:
    def test_v1_router_has_routes(self):
        from ecommerce_ops.api.cart_recovery import router as cart_router
        from ecommerce_ops.api.customer_support import router as support_router
        from ecommerce_ops.api.demo import router as demo_router
        from ecommerce_ops.api.memory import router as mem_router
        from ecommerce_ops.api.observability import router as obs_router
        from ecommerce_ops.api.security import router as sec_router
        from ecommerce_ops.api.shopify import router as shopify_router

        v1 = create_v1_router(
            shopify_router, cart_router, support_router,
            obs_router, mem_router, sec_router, demo_router,
        )
        assert v1.prefix == "/api/v1"
        route_paths = _flatten_route_paths(v1)
        assert "/api/v1/version" in route_paths
