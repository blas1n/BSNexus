"""Integration tests for worker registration and heartbeat flow."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src import models
from backend.src.main import app
from backend.src.storage.database import get_db


# -- Helpers -------------------------------------------------------------------


def _async_iter(items: list):
    """Helper to create an async iterator from a list."""
    async def _gen():
        for item in items:
            yield item
    return _gen()


# -- Tests ---------------------------------------------------------------------


async def test_worker_registration_and_list(db_session: AsyncSession):
    """Register a worker and verify it appears in the worker list."""
    # Create a valid registration token in DB
    token_str = "glrt-integration-test-reg-token"
    reg_token = models.RegistrationToken(
        id=uuid.uuid4(),
        token=token_str,
        name="integration-test-token",
    )
    db_session.add(reg_token)
    await db_session.commit()

    mock_redis = AsyncMock()
    mock_redis.hset = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={})
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.expire = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.delete = AsyncMock()
    mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))

    app.state.redis = mock_redis
    app.state.stream_manager = AsyncMock()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as api_client:
        # Register a worker
        register_resp = await api_client.post(
            "/api/v1/workers/register",
            json={
                "platform": "linux",
                "capabilities": {"python": True},
                "executor_type": "claude-code",
                "registration_token": token_str,
            },
        )

        assert register_resp.status_code == 200
        data = register_resp.json()
        assert "worker_id" in data
        assert "token" in data
        assert len(data["token"]) == 64
        assert data["heartbeat_interval"] == 30
        assert data["streams"]["tasks_queue"] == "tasks:queue"
        assert data["streams"]["tasks_results"] == "tasks:results"
        assert data["streams"]["tasks_qa"] == "tasks:qa"
        assert data["consumer_groups"]["workers"] == "workers"
        assert data["consumer_groups"]["reviewers"] == "reviewers"

        worker_id = data["worker_id"]

        # Simulate listing workers - set up scan_iter to return the worker
        mock_redis.scan_iter = MagicMock(
            return_value=_async_iter([f"worker:{worker_id}"])
        )
        mock_redis.hgetall = AsyncMock(return_value={
            "id": worker_id,
            "name": f"worker-{worker_id[:8]}",
            "platform": "linux",
            "capabilities": '["python"]',
            "executor_type": "claude-code",
            "status": "idle",
            "current_task_id": "",
        })

        list_resp = await api_client.get("/api/v1/workers")
        assert list_resp.status_code == 200
        workers = list_resp.json()
        assert len(workers) == 1
        assert workers[0]["id"] == worker_id
        assert workers[0]["platform"] == "linux"
        assert workers[0]["status"] == "idle"

    app.dependency_overrides.clear()


async def test_worker_heartbeat(db_session: AsyncSession):
    """Register a worker, send heartbeat, verify response."""
    # Create a valid registration token in DB
    token_str = "glrt-integration-heartbeat-token"
    reg_token = models.RegistrationToken(
        id=uuid.uuid4(),
        token=token_str,
        name="heartbeat-test-token",
    )
    db_session.add(reg_token)
    await db_session.commit()

    mock_redis = AsyncMock()
    mock_redis.hset = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={})
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.expire = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.delete = AsyncMock()
    mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))

    app.state.redis = mock_redis
    app.state.stream_manager = AsyncMock()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as api_client:
        # Register a worker
        register_resp = await api_client.post(
            "/api/v1/workers/register",
            json={
                "platform": "darwin",
                "capabilities": {"node": True},
                "executor_type": "claude-code",
                "registration_token": token_str,
            },
        )
        assert register_resp.status_code == 200
        worker_id = register_resp.json()["worker_id"]
        token = register_resp.json()["token"]

        # Set up mock for heartbeat:
        # resolve_token returns the worker_id
        mock_redis.get = AsyncMock(return_value=worker_id)
        # worker exists
        mock_redis.exists = AsyncMock(return_value=1)
        # get_worker data
        mock_redis.hgetall = AsyncMock(return_value={
            "id": worker_id,
            "name": f"worker-{worker_id[:8]}",
            "platform": "darwin",
            "capabilities": '["node"]',
            "executor_type": "claude-code",
            "status": "idle",
            "current_task_id": "",
        })

        # Send heartbeat
        heartbeat_resp = await api_client.post(
            f"/api/v1/workers/{worker_id}/heartbeat",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert heartbeat_resp.status_code == 200
        hb_data = heartbeat_resp.json()
        assert hb_data["status"] == "idle"
        assert hb_data["pending_tasks"] == 0

    app.dependency_overrides.clear()
