import json
import logging
import re
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from ecommerce_ops.api.metrics import (
    METRIC_HTTP_DURATION,
    METRIC_HTTP_REQUESTS,
    METRIC_RATE_LIMIT_REJECTED,
)
from ecommerce_ops.config import Environment, settings
from ecommerce_ops.infra.rate_limiter import check_rate_limit
from ecommerce_ops.memory.cache import _get_ttl, cache
from ecommerce_ops.security.hardening import (
    InputSanitizationMiddleware,
    SecurityHeadersMiddleware,
)

logger = logging.getLogger("ecommerce_ops.api.middleware")

# Regex patterns for normalizing dynamic path segments so Prometheus
# label cardinality stays bounded (H7).
_DYNAMIC_PATH_PATTERNS = [
    (re.compile(r"^/approvals/[0-9a-f-]+$"), "/approvals/{id}"),
    (re.compile(r"^/approvals/[0-9a-f-]+/audit$"), "/approvals/{id}/audit"),
    (re.compile(r"^/tasks/[0-9a-f-]+$"), "/tasks/{id}"),
    (re.compile(r"^/ws/[^/]+$"), "/ws/{ticket}"),
    (re.compile(r"^/agents/[^/]+$"), "/agents/{name}"),
]


def _normalize_endpoint(path: str) -> str:
    """Normalize a request path for Prometheus labels.

    Replaces dynamic segments (UUIDs, IDs, tokens) with placeholders so
    that the number of distinct labels stays bounded.
    """
    for pattern, replacement in _DYNAMIC_PATH_PATTERNS:
        if pattern.match(path):
            return replacement
    return path


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start
        endpoint = _normalize_endpoint(request.url.path)
        METRIC_HTTP_REQUESTS.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code,
        ).inc()
        METRIC_HTTP_DURATION.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.info("Request started: %s %s [%s]", request.method, request.url.path, request_id)
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start
        logger.info(
            "Request completed: %s %s -> %s [%s] (%.3fs)",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            duration,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Rate limiting is always-on for real environments (production,
        # development, staging, demo). Only the automated test harness is
        # exempt, since it issues far more than RATE_LIMIT_PER_MINUTE
        # requests per minute from a single source.
        if settings.ENV == Environment.TESTING:
            return await call_next(request)

        client_ip = self._get_trusted_client_ip(request)
        info = await check_rate_limit(
            client_ip,
            settings.RATE_LIMIT_PER_MINUTE,
            max_requests_per_hour=settings.RATE_LIMIT_PER_HOUR,
        )

        headers = {
            "X-RateLimit-Limit": str(info.limit),
            "X-RateLimit-Remaining": str(info.remaining),
            "X-RateLimit-Reset": str(int(info.reset_at)),
            "X-RateLimit-Hourly-Limit": str(info.hourly_limit),
            "X-RateLimit-Hourly-Remaining": str(info.hourly_remaining),
            "X-RateLimit-Hourly-Reset": str(int(info.hourly_reset_at)),
        }

        if not info.allowed:
            METRIC_RATE_LIMIT_REJECTED.inc()
            logger.warning(
                "Rate limit exceeded for %s (%d req/min, %d req/hr)",
                client_ip,
                info.remaining,
                info.hourly_remaining,
            )
            return Response(
                status_code=429,
                content='{"detail":"Rate limit exceeded. Try again later."}',
                media_type="application/json",
                headers=headers,
            )

        response = await call_next(request)
        for header, value in headers.items():
            response.headers[header] = value
        return response

    def _get_trusted_client_ip(self, request: Request) -> str:
        """Extract the real client IP.

        Only honors X-Forwarded-For when the request originates from a
        trusted proxy (or when in testing / local mode). This prevents
        clients from spoofing their IP to bypass rate limits (H10).
        """
        direct_ip = request.client.host if request.client else "unknown"

        if settings.ENV == Environment.TESTING:
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return direct_ip

        if not settings.TRUSTED_PROXIES:
            return direct_ip

        import ipaddress

        try:
            client_addr = ipaddress.ip_address(direct_ip)
        except ValueError:
            return direct_ip

        for proxy_cidr in settings.TRUSTED_PROXIES:
            try:
                if client_addr in ipaddress.ip_network(proxy_cidr, strict=False):
                    forwarded = request.headers.get("X-Forwarded-For", "")
                    if forwarded:
                        return forwarded.split(",")[0].strip()
            except ValueError:
                logger.warning("Invalid TRUSTED_PROXIES CIDR: %s", proxy_cidr)

        return direct_ip


MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in ("GET", "HEAD", "DELETE", "OPTIONS"):
            return await call_next(request)

        content_length = request.headers.get("content-length")
        try:
            if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
                return Response(
                    status_code=413,
                    content='{"detail":"Request body too large. Max 10MB."}',
                    media_type="application/json",
                )
        except (ValueError, TypeError):
            pass

        return await call_next(request)


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method != "GET":
            return await call_next(request)

        ttl = _get_ttl(request.url.path)
        if ttl == 0:
            return await call_next(request)

        cached = await cache.get_cached_response(
            request.method, request.url.path, request.url.query
        )
        if cached is not None:
            status_code, body = cached
            return Response(
                content=json.dumps(body),
                status_code=status_code,
                media_type="application/json",
                headers={"X-Cache": "HIT"},
            )

        response = await call_next(request)

        if response.status_code == 200 and response.media_type == "application/json":
            try:
                body = json.loads(response.body)
                await cache.set_cached_response(
                    request.method, request.url.path, request.url.query, response.status_code, body
                )
            except (RuntimeError, json.JSONDecodeError):
                pass

        response.headers["X-Cache"] = "MISS"
        return response


def setup_middleware(app: FastAPI):
    allowed_origins = settings.CORS_ORIGINS
    if not allowed_origins:
        if settings.ENV == Environment.PRODUCTION:
            raise RuntimeError(
                "CORS_ORIGINS must be explicitly set in production. "
                "Configure allowed origins in environment variables."
            )
        # Development fallback only
        allowed_origins = ["http://localhost:3000", "http://localhost:5173"]

    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(InputSanitizationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ResponseCacheMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
