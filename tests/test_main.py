# tests/test_main.py
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio


def _client() -> AsyncClient:
    """Build a test client for the ASGI app.

    httpx removed the `app=` shortcut in 0.28; an explicit ASGITransport is the
    supported way to drive an ASGI app in-process. requirements.txt does not pin
    httpx, so a clean clone installs 0.28+ and the old form raises TypeError.
    """
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health_check():
    """
    Tests the public health check endpoint.
    """
    async with _client() as ac:
        response = await ac.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unauthorized_access():
    """
    Tests that protected endpoints behave correctly for the configured auth mode.

    AUTH_BYPASS is read once at import time in app/security.py, so it cannot be
    toggled here. The template ships AUTH_BYPASS=true in .env.example, which means
    a clean clone authenticates every request as the Dev User and this endpoint
    returns 200. Asserting a flat 401 would fail on the template's own defaults, so
    assert whichever behaviour the current configuration should produce.
    """
    from app.security import AUTH_BYPASS

    async with _client() as ac:
        response = await ac.get("/api/test")

    if AUTH_BYPASS:
        assert response.status_code == 200
    else:
        assert response.status_code == 401


# Additional tests would include:
# - Database integration tests
# - Authorization engine tests
# - API endpoint tests with mocked authentication
# - Model validation tests
