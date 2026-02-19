"""Tests for RateLimiter and RateLimitMiddleware."""

import time

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.src.core.rate_limiter import RateLimitBucket, RateLimitConfig, RateLimitMiddleware, RateLimiter


class TestRateLimitBucket:
    def test_consume_within_limit(self):
        bucket = RateLimitBucket(tokens=5.0, max_tokens=10.0, refill_rate=1.0)
        assert bucket.consume() is True
        assert bucket.tokens < 5.0

    def test_consume_exhausts_tokens(self):
        bucket = RateLimitBucket(tokens=1.0, max_tokens=10.0, refill_rate=1.0)
        assert bucket.consume() is True
        assert bucket.consume() is False

    def test_retry_after(self):
        bucket = RateLimitBucket(tokens=0.0, max_tokens=10.0, refill_rate=1.0)
        assert bucket.retry_after > 0.0

    def test_retry_after_zero_when_available(self):
        bucket = RateLimitBucket(tokens=5.0, max_tokens=10.0, refill_rate=1.0)
        assert bucket.retry_after == 0.0

    def test_tokens_refill(self):
        bucket = RateLimitBucket(
            tokens=0.0,
            max_tokens=10.0,
            refill_rate=100.0,  # fast refill for test
            last_refill=time.monotonic() - 1.0,  # 1 second ago
        )
        assert bucket.consume() is True  # Should have refilled


class TestRateLimiter:
    def test_allows_within_limit(self):
        limiter = RateLimiter(rate_limits={"/api": RateLimitConfig(requests_per_second=10.0, burst_size=5)})
        allowed, _ = limiter.check("client-1", "/api/v1/tasks")
        assert allowed is True

    def test_blocks_after_burst(self):
        limiter = RateLimiter(rate_limits={"/api": RateLimitConfig(requests_per_second=10.0, burst_size=2)})
        limiter.check("client-1", "/api/v1/tasks")
        limiter.check("client-1", "/api/v1/tasks")
        allowed, retry_after = limiter.check("client-1", "/api/v1/tasks")
        assert allowed is False
        assert retry_after > 0

    def test_different_clients_independent(self):
        limiter = RateLimiter(rate_limits={"/api": RateLimitConfig(requests_per_second=10.0, burst_size=1)})
        limiter.check("client-1", "/api/v1/tasks")
        allowed, _ = limiter.check("client-2", "/api/v1/tasks")
        assert allowed is True

    def test_path_specific_limits(self):
        limiter = RateLimiter(rate_limits={
            "/api/v1/architect": RateLimitConfig(requests_per_second=1.0, burst_size=1),
            "/api": RateLimitConfig(requests_per_second=100.0, burst_size=100),
        })
        # Exhaust architect limit
        limiter.check("client-1", "/api/v1/architect/sessions")
        allowed, _ = limiter.check("client-1", "/api/v1/architect/sessions")
        assert allowed is False

        # General API should still work
        allowed, _ = limiter.check("client-1", "/api/v1/tasks")
        assert allowed is True


class TestRateLimitMiddleware:
    @pytest.fixture
    def app(self):
        async def homepage(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        starlette_app = Starlette(routes=[
            Route("/", homepage),
            Route("/api/test", homepage),
            Route("/health", homepage),
        ])
        limiter = RateLimiter(rate_limits={"/api": RateLimitConfig(requests_per_second=10.0, burst_size=2)})
        starlette_app.add_middleware(RateLimitMiddleware, rate_limiter=limiter, exempt_paths={"/health"})
        return starlette_app

    async def test_allows_normal_requests(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/test")
        assert resp.status_code == 200

    async def test_blocks_excessive_requests(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/api/test")
            await client.get("/api/test")
            resp = await client.get("/api/test")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    async def test_exempt_paths_not_limited(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(10):
                resp = await client.get("/health")
                assert resp.status_code == 200
