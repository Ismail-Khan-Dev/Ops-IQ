"""Tests for security/audit.py, security/webhook.py."""
import base64
import hashlib
import hmac

from ecommerce_ops.security.audit import AuditEntry, AuditLogger
from ecommerce_ops.security.models import SecurityEvent
from ecommerce_ops.security.webhook import InputSanitizer, WebhookVerifier

# ── AuditLogger tests ──────────────────────────────────────


class TestAuditLogger:
    def setup_method(self):
        self.logger = AuditLogger()

    def test_assess_risk_level_violation(self):
        event = SecurityEvent(
            event_type="security_violation", action="test",
            resource="test", success=False,
        )
        assert self.logger._assess_risk_level(event) == "critical"

    def test_assess_risk_level_failure(self):
        event = SecurityEvent(
            event_type="authentication", action="login",
            resource="auth", success=False,
        )
        assert self.logger._assess_risk_level(event) == "high"

    def test_assess_risk_level_config_change(self):
        event = SecurityEvent(
            event_type="config_change", action="update",
            resource="config", success=True,
        )
        assert self.logger._assess_risk_level(event) == "medium"

    def test_assess_risk_level_authz(self):
        event = SecurityEvent(
            event_type="authorization", action="access",
            resource="api", success=True,
        )
        assert self.logger._assess_risk_level(event) == "medium"

    def test_assess_risk_level_low(self):
        event = SecurityEvent(
            event_type="data_access", action="read",
            resource="db", success=True,
        )
        assert self.logger._assess_risk_level(event) == "low"

    def test_sanitize_details_redacts_sensitive(self):
        details = {"password": "secret123", "api_key": "key-abc", "normal_field": "keep"}
        sanitized = self.logger._sanitize_details(details)
        assert sanitized["password"] == "***REDACTED***"
        assert sanitized["api_key"] == "***REDACTED***"
        assert sanitized["normal_field"] == "keep"

    def test_sanitize_nested_dict(self):
        details = {"user": {"password": "pw", "name": "John"}}
        sanitized = self.logger._sanitize_details(details)
        assert sanitized["user"]["password"] == "***REDACTED***"
        assert sanitized["user"]["name"] == "John"

    def test_sanitize_token_in_key(self):
        details = {"auth_token": "abc", "bearer_token": "xyz"}
        sanitized = self.logger._sanitize_details(details)
        assert sanitized["auth_token"] == "***REDACTED***"
        assert sanitized["bearer_token"] == "***REDACTED***"

    def test_log_event_returns_entry(self):
        event = SecurityEvent(
            event_type="authentication", action="login",
            resource="auth", success=True, user_id="u1",
        )
        entry = self.logger.log_event(event)
        assert isinstance(entry, AuditEntry)
        assert entry.event_type == "authentication"
        assert entry.action == "login"
        assert entry.success is True

    def test_log_auth_event(self):
        entry = self.logger.log_auth_event("login", user_id="u1", success=True)
        assert entry.event_type == "authentication"
        assert entry.resource == "auth"

    def test_log_permission_event(self):
        entry = self.logger.log_permission_event("access", user_id="u1", resource="api")
        assert entry.event_type == "authorization"

    def test_log_data_access(self):
        entry = self.logger.log_data_access("read", "orders", resource_id="o1")
        assert entry.event_type == "data_access"

    def test_log_config_change(self):
        entry = self.logger.log_config_change("update", changes={"key": "value"})
        assert entry.event_type == "config_change"

    def test_log_security_violation(self):
        entry = self.logger.log_security_violation("injection", "api")
        assert entry.event_type == "security_violation"
        assert entry.success is False


# ── WebhookVerifier tests ──────────────────────────────────


class TestWebhookVerifier:
    def setup_method(self):
        self.secret = "test-secret-key-123"
        self.verifier = WebhookVerifier(self.secret)

    def test_verify_valid_hmac(self):
        body = b'{"test": "data"}'
        computed = hmac.new(self.secret.encode(), body, hashlib.sha256).digest()
        hmac_b64 = base64.b64encode(computed).decode()
        assert self.verifier.verify(body, hmac_b64) is True

    def test_verify_invalid_hmac(self):
        assert self.verifier.verify(b"body", "invalid-hmac-value") is False

    def test_verify_missing_hmac(self):
        assert self.verifier.verify(b"body", "") is False

    def test_verify_none_hmac(self):
        assert self.verifier.verify(b"body", None) is False

    def test_verify_topic_allowed(self):
        assert self.verifier.verify_shopify_topic("orders/create", ["orders/create"]) is True

    def test_verify_topic_not_allowed(self):
        assert self.verifier.verify_shopify_topic("orders/create", ["products/update"]) is False

    def test_verify_topic_no_restriction(self):
        assert self.verifier.verify_shopify_topic("anything") is True

    def test_secret_bytes_input(self):
        verifier = WebhookVerifier(b"raw-bytes-secret")
        assert verifier.secret == b"raw-bytes-secret"


# ── InputSanitizer tests ───────────────────────────────────


class TestInputSanitizer:
    def test_sanitize_string_normal(self):
        assert InputSanitizer.sanitize_string("hello") == "hello"

    def test_sanitize_string_max_length(self):
        result = InputSanitizer.sanitize_string("a" * 20000, max_length=100)
        assert len(result) == 100

    def test_sanitize_string_strips_whitespace(self):
        assert InputSanitizer.sanitize_string("  hello  ") == "hello"

    def test_sanitize_string_non_string(self):
        result = InputSanitizer.sanitize_string(12345)
        assert result == "12345"

    def test_sanitize_dict_normal(self):
        data = {"key": "value", "num": 42}
        result = InputSanitizer.sanitize_dict(data)
        assert result["key"] == "value"
        assert result["num"] == 42

    def test_sanitize_dict_max_depth(self):
        data = {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}
        result = InputSanitizer.sanitize_dict(data, max_depth=2)
        assert "a" in result
        assert "b" in result["a"]
        assert result["a"]["b"] == {}

    def test_sanitize_dict_truncates_list(self):
        data = {"items": list(range(200))}
        result = InputSanitizer.sanitize_dict(data)
        assert len(result["items"]) == 100

    def test_detect_injection_script(self):
        assert InputSanitizer.detect_injection('<script>alert("xss")</script>') is True

    def test_detect_injection_sql(self):
        assert InputSanitizer.detect_injection("1; DROP TABLE users") is True

    def test_detect_injection_template(self):
        assert InputSanitizer.detect_injection("{{config}}") is True

    def detect_injection_safe(self):
        assert InputSanitizer.detect_injection("Hello world") is False
