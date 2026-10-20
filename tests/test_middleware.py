
import pytest
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.testclient import TestClient

from ecommerce_ops.api.middleware import BodySizeLimitMiddleware


@pytest.fixture
def app():
    async def homepage(request):
        return Response("OK", media_type="text/plain")

    app = Starlette()
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_route("/", homepage, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestBodySizeLimitMiddleware:
    def test_get_request_passes_through(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_delete_request_passes_through(self, client):
        response = client.delete("/")
        assert response.status_code != 413

    def test_options_request_passes_through(self, client):
        response = client.options("/")
        assert response.status_code != 413

    def test_head_request_passes_through(self, client):
        response = client.head("/")
        assert response.status_code != 413

    def test_post_without_content_length_passes(self, client):
        response = client.post("/", content=b"small")
        assert response.status_code == 200

    def test_post_with_small_body_passes(self, client):
        response = client.post(
            "/",
            content=b"x" * 1024,
            headers={"Content-Length": "1024"},
        )
        assert response.status_code == 200

    def test_post_with_large_body_rejected(self, client):
        large_size = 11 * 1024 * 1024  # 11 MB
        response = client.post(
            "/",
            content=b"x" * 100,
            headers={"Content-Length": str(large_size)},
        )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_put_with_large_body_rejected(self, client):
        large_size = 20 * 1024 * 1024  # 20 MB
        response = client.put(
            "/",
            content=b"x" * 100,
            headers={"Content-Length": str(large_size)},
        )
        assert response.status_code == 413

    def test_patch_with_large_body_rejected(self, client):
        large_size = 50 * 1024 * 1024  # 50 MB
        response = client.patch(
            "/",
            content=b"x" * 100,
            headers={"Content-Length": str(large_size)},
        )
        assert response.status_code == 413

    def test_exactly_10mb_passes(self, client):
        exact_size = 10 * 1024 * 1024  # Exactly 10 MB
        response = client.post(
            "/",
            content=b"x" * 100,
            headers={"Content-Length": str(exact_size)},
        )
        assert response.status_code == 200

    def test_over_10mb_rejected(self, client):
        over_size = 10 * 1024 * 1024 + 1  # 10 MB + 1 byte
        response = client.post(
            "/",
            content=b"x" * 100,
            headers={"Content-Length": str(over_size)},
        )
        assert response.status_code == 413

    def test_rejection_returns_json(self, client):
        large_size = 15 * 1024 * 1024
        response = client.post(
            "/",
            content=b"x" * 100,
            headers={"Content-Length": str(large_size)},
        )
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert "detail" in data
