"""
Webhook Verification - Shopify HMAC signature verification.
"""

import hashlib
import hmac
import logging
from typing import Optional

logger = logging.getLogger("ecommerce_ops.security.webhook")


class WebhookVerifier:
    """Verify Shopify webhook HMAC signatures."""

    def __init__(self, secret: str):
        self.secret = secret.encode("utf-8") if isinstance(secret, str) else secret

    def verify(self, body: bytes, hmac_header: str) -> bool:
        """
        Verify webhook HMAC signature.

        Args:
            body: Raw request body bytes
            hmac_header: X-Shopify-Hmac-Sha256 header value

        Returns:
            True if signature is valid
        """
        if not hmac_header:
            logger.warning("Missing HMAC header")
            return False

        try:
            computed = hmac.new(
                self.secret,
                body,
                hashlib.sha256,
            ).digest()

            import base64

            computed_b64 = base64.b64encode(computed).decode("utf-8")

            is_valid = hmac.compare_digest(computed_b64, hmac_header)

            if not is_valid:
                logger.warning("HMAC verification failed")

            return is_valid

        except Exception as e:
            logger.error(f"HMAC verification error: {e}")
            return False

    def verify_shopify_topic(self, topic: str, allowed_topics: Optional[list] = None) -> bool:
        """Verify webhook topic is allowed."""
        if not allowed_topics:
            return True

        return topic in allowed_topics


class InputSanitizer:
    """Sanitize and validate webhook input data."""

    @staticmethod
    def sanitize_string(value: str, max_length: int = 10000) -> str:
        """Sanitize a string value."""
        if not isinstance(value, str):
            return str(value)[:max_length]
        return value[:max_length].strip()

    @staticmethod
    def sanitize_dict(data: dict, max_depth: int = 5) -> dict:
        """Recursively sanitize a dictionary."""
        if max_depth <= 0:
            return {}

        sanitized = {}
        for key, value in data.items():
            key = str(key)[:100]
            if isinstance(value, dict):
                sanitized[key] = InputSanitizer.sanitize_dict(value, max_depth - 1)
            elif isinstance(value, list):
                sanitized[key] = [
                    InputSanitizer.sanitize_dict(item, max_depth - 1)
                    if isinstance(item, dict)
                    else str(item)[:1000]
                    if isinstance(item, str)
                    else item
                    for item in value[:100]
                ]
            elif isinstance(value, str):
                sanitized[key] = value[:10000]
            else:
                sanitized[key] = value
        return sanitized

    @staticmethod
    def detect_injection(value: str) -> bool:
        """Detect potential injection attempts."""
        dangerous_patterns = [
            "<script",
            "javascript:",
            "onerror=",
            "onload=",
            "UNION SELECT",
            "DROP TABLE",
            "INSERT INTO",
            "{{",
            "{%",
            "${",
            "<%",
            "\\x00",
            "\\n\\r",
        ]
        value_lower = value.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in value_lower:
                logger.warning(f"Potential injection detected: {pattern}")
                return True
        return False
