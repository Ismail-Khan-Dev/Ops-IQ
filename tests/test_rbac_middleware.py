import os

os.environ.setdefault("ENV", "testing")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-key")

from ecommerce_ops.security.rbac_middleware import AccessLevel, get_required_access_level


class TestGetRequiredAccessLevel:
    def test_get_required_access_level_public(self):
        assert get_required_access_level("/health") == AccessLevel.PUBLIC

    def test_get_required_access_level_viewer(self):
        assert get_required_access_level("/api/agents/status") == AccessLevel.VIEWER

    def test_get_required_access_level_operator(self):
        assert get_required_access_level("/api/run") == AccessLevel.OPERATOR

    def test_get_required_access_level_admin(self):
        assert get_required_access_level("/security/roles") == AccessLevel.ADMIN

    def test_get_required_access_level_unknown_path(self):
        assert get_required_access_level("/unknown/path") == AccessLevel.OPERATOR

    def test_get_required_access_level_nested(self):
        assert get_required_access_level("/cart-recovery/analyze/batch") == AccessLevel.OPERATOR
