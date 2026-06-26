"""API integration tests.

Requires MySQL and Redis to be running with the devdb database available.
Configure connection via src/.env or environment variables.

Skip these tests when infrastructure is not available:
    pytest -m "not integration"
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.integration
class TestUserAPI:
    """Integration tests for user endpoints.

    These tests require a running MySQL and Redis instance.
    They should be run against a dedicated test database.
    """

    async def test_login_user_not_found(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/user/login",
                json={"username": "nonexistent", "password": "test123"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] != 0  # non-zero = business error

    async def test_health_check(self) -> None:
        """Simple health check to verify app boots correctly."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/openapi.json")
        assert resp.status_code == 200
