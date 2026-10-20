"""
Security Headers and Rate Limiting
Middleware for security hardening.
"""

import logging
import time
from typing import ClassVar, Dict, List

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger("ecommerce_ops.security.hardening")

ALLOWED_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3200",
    "http://localhost:8080",
    "https://ops-iq.dev",
]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers."""

    SECURITY_HEADERS: ClassVar[Dict[str, str]] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com;",
    }

    CORS_HEADERS: ClassVar[Dict[str, str]] = {
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key, X-Operator-Id",
        "Access-Control-Max-Age": "86400",
    }

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method == "OPTIONS":
            response = Response(status_code=200, headers=self.CORS_HEADERS)
            origin = request.headers.get("origin", "")
            if origin in ALLOWED_ORIGINS:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

        response = await call_next(request)

        for header, value in self.SECURITY_HEADERS.items():
            response.headers[header] = value

        origin = request.headers.get("origin", "")
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"

        return response


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """Middleware for input sanitization."""

    DANGEROUS_PATTERNS: ClassVar[List[str]] = [
        "<script",
        "javascript:",
        "onerror=",
        "onload=",
        "eval(",
        "document.cookie",
        "window.location",
    ]

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        url = str(request.url)
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in url.lower():
                logger.warning(
                    "Blocked request with dangerous pattern: %s from %s",
                    pattern,
                    request.client.host if request.client else "unknown",
                )
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid request"},
                )

        for _header_name, header_value in request.headers.items():
            for pattern in self.DANGEROUS_PATTERNS:
                if pattern.lower() in str(header_value).lower():
                    logger.warning(
                        "Blocked request with dangerous header pattern: %s",
                        pattern,
                    )
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Invalid request headers"},
                    )

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request logging."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        start_time = time.time()

        logger.info(
            "Request started: %s %s from %s",
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
        )

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "Request completed: %s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response
