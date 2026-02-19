"""Tests for SecurityHeadersMiddleware."""

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.src.core.security_headers import SecurityHeadersMiddleware


def make_app(**kwargs):
    """Create a minimal Starlette app with security headers middleware."""

    async def homepage(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(SecurityHeadersMiddleware, **kwargs)
    return app


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def app_with_hsts():
    return make_app(enable_hsts=True, hsts_max_age=86400, hsts_preload=True)


async def test_default_security_headers(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")

    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-XSS-Protection"] == "1; mode=block"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in resp.headers
    assert "Permissions-Policy" in resp.headers
    assert resp.headers["X-Permitted-Cross-Domain-Policies"] == "none"
    assert "no-store" in resp.headers["Cache-Control"]


async def test_hsts_disabled_by_default(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")

    assert "Strict-Transport-Security" not in resp.headers


async def test_hsts_enabled(app_with_hsts):
    async with AsyncClient(transport=ASGITransport(app=app_with_hsts), base_url="http://test") as client:
        resp = await client.get("/")

    hsts = resp.headers["Strict-Transport-Security"]
    assert "max-age=86400" in hsts
    assert "includeSubDomains" in hsts
    assert "preload" in hsts


async def test_custom_csp():
    custom_csp = "default-src 'none'"
    app = make_app(content_security_policy=custom_csp)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")

    assert resp.headers["Content-Security-Policy"] == custom_csp


async def test_custom_permissions_policy():
    custom_pp = "camera=(), microphone=()"
    app = make_app(permissions_policy=custom_pp)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")

    assert resp.headers["Permissions-Policy"] == custom_pp
