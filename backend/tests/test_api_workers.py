from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.src.main import app


# ── Helpers ──────────────────────────────────────────────────────────────


async def _async_iter(items: list):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def mock_redis() -> AsyncMock:
    """Create a mock Redis client for the worker API tests."""
    r = AsyncMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.hget = AsyncMock(return_value=None)
    r.expire = AsyncMock()
    r.exists = AsyncMock(return_value=1)
    r.set = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.delete = AsyncMock()
    r.scan_iter = MagicMock(return_value=_async_iter([]))
    return r


@pytest_asyncio.fixture
async def api_client(mock_redis: AsyncMock) -> AsyncGenerator[AsyncClient]:
    """Create an HTTP test client with a mocked Redis on app.state."""
    app.state.redis = mock_redis
    app.state.stream_manager = AsyncMock()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# ── POST /api/workers/register ───────────────────────────────────────────


async def test_register_worker_success(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """POST /api/workers/register should return worker_id, token, and stream info."""
    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
            "capabilities": {"python": True},
            "executor_type": "claude-code",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "worker_id" in data
    assert "token" in data
    assert len(data["token"]) == 64
    assert data["heartbeat_interval"] == 30
    assert data["streams"]["tasks_queue"] == "tasks:queue"
    assert data["streams"]["tasks_results"] == "tasks:results"
    assert data["streams"]["tasks_qa"] == "tasks:qa"
    assert data["consumer_groups"]["workers"] == "workers"
    assert data["consumer_groups"]["reviewers"] == "reviewers"

    # Redis should have been called
    mock_redis.hset.assert_called_once()
    mock_redis.expire.assert_called_once()
    mock_redis.set.assert_called_once()


async def test_register_worker_auto_name(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """When name is not provided, a default name should be generated."""
    response = await api_client.post(
        "/api/v1/workers/register",
        json={"platform": "darwin"},
    )

    assert response.status_code == 200
    data = response.json()
    # Name should start with "worker-" followed by first 8 chars of uuid
    worker_id = data["worker_id"]
    assert worker_id  # should be a valid UUID string


# ── POST /api/workers/{id}/heartbeat ─────────────────────────────────────


async def test_heartbeat_with_valid_token(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """Heartbeat with valid token should return status and pending_tasks."""
    worker_id = str(uuid.uuid4())

    # resolve_token returns the worker_id
    mock_redis.get.return_value = worker_id
    # worker exists
    mock_redis.exists.return_value = 1
    # get_worker data
    mock_redis.hgetall.return_value = {
        "id": worker_id,
        "name": "W1",
        "platform": "linux",
        "capabilities": "[]",
        "executor_type": "claude-code",
        "status": "idle",
        "current_task_id": "",
    }

    response = await api_client.post(
        f"/api/v1/workers/{worker_id}/heartbeat",
        headers={"Authorization": "Bearer valid-token-here"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "idle"
    assert data["pending_tasks"] == 0


async def test_heartbeat_with_invalid_token(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """Heartbeat with invalid token should return 401."""
    worker_id = str(uuid.uuid4())

    # resolve_token returns None (invalid token)
    mock_redis.get.return_value = None

    response = await api_client.post(
        f"/api/v1/workers/{worker_id}/heartbeat",
        headers={"Authorization": "Bearer bad-token"},
    )

    assert response.status_code == 401
    assert "Invalid token" in response.json()["detail"]


async def test_heartbeat_missing_auth_header(api_client: AsyncClient) -> None:
    """Heartbeat without Authorization header should return 401."""
    worker_id = str(uuid.uuid4())

    response = await api_client.post(f"/api/v1/workers/{worker_id}/heartbeat")

    assert response.status_code == 401
    assert "Missing or invalid token" in response.json()["detail"]


async def test_heartbeat_token_mismatch(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """Heartbeat where token resolves to a different worker should return 403."""
    worker_id = str(uuid.uuid4())
    other_worker_id = str(uuid.uuid4())

    # Token resolves to a different worker
    mock_redis.get.return_value = other_worker_id

    response = await api_client.post(
        f"/api/v1/workers/{worker_id}/heartbeat",
        headers={"Authorization": "Bearer some-token"},
    )

    assert response.status_code == 403
    assert "Token does not match" in response.json()["detail"]


# ── GET /api/workers ─────────────────────────────────────────────────────


async def test_list_workers(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """GET /api/workers/ should return list of active workers."""
    mock_redis.scan_iter = MagicMock(
        return_value=_async_iter(["worker:w-1", "worker:w-2"])
    )

    async def hgetall_side_effect(key: str) -> dict:
        if key == "worker:w-1":
            return {
                "id": "w-1",
                "name": "W1",
                "platform": "linux",
                "capabilities": "[]",
                "executor_type": "claude-code",
                "status": "idle",
                "current_task_id": "",
            }
        if key == "worker:w-2":
            return {
                "id": "w-2",
                "name": "W2",
                "platform": "darwin",
                "capabilities": '["python"]',
                "executor_type": "claude-code",
                "status": "busy",
                "current_task_id": "task-1",
            }
        return {}

    mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

    response = await api_client.get("/api/v1/workers/")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    ids = {w["id"] for w in data}
    assert ids == {"w-1", "w-2"}


async def test_list_workers_empty(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """GET /api/workers/ with no registered workers returns empty list."""
    mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))

    response = await api_client.get("/api/v1/workers/")

    assert response.status_code == 200
    assert response.json() == []


# ── DELETE /api/workers/{id} ─────────────────────────────────────────────


async def test_deregister_worker(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """DELETE /api/workers/{id} should deregister the worker."""
    worker_id = str(uuid.uuid4())
    mock_redis.hget.return_value = "some-token"

    response = await api_client.delete(f"/api/v1/workers/{worker_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["detail"] == "Worker deregistered"
    assert data["worker_id"] == worker_id
    assert mock_redis.delete.call_count == 2  # worker hash + token key
