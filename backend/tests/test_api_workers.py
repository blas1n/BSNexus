from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src import models
from backend.src.main import app
from backend.src.storage.database import get_db


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
async def api_client(mock_redis: AsyncMock, db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Create an HTTP test client with mocked Redis and real DB session."""
    app.state.redis = mock_redis
    app.state.stream_manager = AsyncMock()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def valid_registration_token(db_session: AsyncSession) -> str:
    """Create a valid registration token in the DB and return the token string."""
    token_str = "glrt-test-valid-token-1234567890"
    token = models.RegistrationToken(
        id=uuid.uuid4(),
        token=token_str,
        name="test-token",
    )
    db_session.add(token)
    await db_session.commit()
    return token_str


# ── POST /api/workers/register ───────────────────────────────────────────


async def test_register_worker_success(
    api_client: AsyncClient, mock_redis: AsyncMock, valid_registration_token: str
) -> None:
    """POST /api/workers/register should return worker_id, token, and stream info."""
    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
            "capabilities": {"python": True},
            "executor_type": "claude-code",
            "registration_token": valid_registration_token,
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


async def test_register_worker_auto_name(
    api_client: AsyncClient, mock_redis: AsyncMock, valid_registration_token: str
) -> None:
    """When name is not provided, a default name should be generated."""
    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "darwin",
            "registration_token": valid_registration_token,
        },
    )

    assert response.status_code == 200
    data = response.json()
    # Name should start with "worker-" followed by first 8 chars of uuid
    worker_id = data["worker_id"]
    assert worker_id  # should be a valid UUID string


async def test_register_worker_invalid_token(api_client: AsyncClient) -> None:
    """POST /api/workers/register with invalid token should return 401."""
    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
            "registration_token": "glrt-invalid-token",
        },
    )

    assert response.status_code == 401
    assert "Invalid registration token" in response.json()["detail"]


async def test_register_worker_revoked_token(api_client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/workers/register with revoked token should return 401."""
    token_str = "glrt-revoked-token-1234567890"
    token = models.RegistrationToken(
        id=uuid.uuid4(),
        token=token_str,
        name="revoked-token",
        revoked=True,
    )
    db_session.add(token)
    await db_session.commit()

    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
            "registration_token": token_str,
        },
    )

    assert response.status_code == 401
    assert "revoked" in response.json()["detail"]


async def test_register_worker_missing_token(api_client: AsyncClient) -> None:
    """POST /api/workers/register without registration_token should return 422."""
    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
        },
    )

    assert response.status_code == 422


# ── POST /api/workers/register (re-registration) ────────────────────────


async def test_re_register_with_valid_token(
    api_client: AsyncClient, mock_redis: AsyncMock, valid_registration_token: str, db_session: AsyncSession
) -> None:
    """Re-register with existing worker_id + valid worker_token should keep same ID."""
    existing_id = str(uuid.uuid4())
    existing_token = "a" * 64

    # Pre-insert worker in DB (required for re-registration validation)
    from datetime import datetime, timezone

    db_session.add(models.Worker(
        id=uuid.UUID(existing_id), name="w1", platform="linux",
        executor_type="claude-code", status=models.WorkerStatus.idle,
        registered_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    # resolve_token returns the existing worker_id (token still valid)
    mock_redis.get.return_value = existing_id

    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
            "registration_token": valid_registration_token,
            "worker_id": existing_id,
            "worker_token": existing_token,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["worker_id"] == existing_id


async def test_re_register_with_expired_token(
    api_client: AsyncClient, mock_redis: AsyncMock, valid_registration_token: str, db_session: AsyncSession
) -> None:
    """Re-register with expired worker_token but valid registration_token should keep same ID."""
    existing_id = str(uuid.uuid4())

    # Pre-insert worker in DB (required for re-registration validation)
    from datetime import datetime, timezone

    db_session.add(models.Worker(
        id=uuid.UUID(existing_id), name="w1", platform="linux",
        executor_type="claude-code", status=models.WorkerStatus.idle,
        registered_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    # resolve_token returns None (token expired)
    mock_redis.get.return_value = None

    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
            "registration_token": valid_registration_token,
            "worker_id": existing_id,
            "worker_token": "expired-token",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["worker_id"] == existing_id


async def test_re_register_unknown_worker_returns_404(
    api_client: AsyncClient, mock_redis: AsyncMock, valid_registration_token: str
) -> None:
    """Re-register with a worker_id not in DB should return 404."""
    unknown_id = str(uuid.uuid4())

    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
            "registration_token": valid_registration_token,
            "worker_id": unknown_id,
        },
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


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


async def test_list_workers(
    api_client: AsyncClient, mock_redis: AsyncMock, db_session: AsyncSession
) -> None:
    """GET /api/v1/workers should return DB workers with Redis status merged."""
    from datetime import datetime, timezone

    w1_id = uuid.uuid4()
    w2_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Insert workers into DB
    db_session.add(models.Worker(
        id=w1_id, name="W1", platform="linux", capabilities=[],
        executor_type="claude-code", status=models.WorkerStatus.idle,
        registered_at=now, last_heartbeat=now,
    ))
    db_session.add(models.Worker(
        id=w2_id, name="W2", platform="darwin", capabilities=["python"],
        executor_type="claude-code", status=models.WorkerStatus.idle,
        registered_at=now, last_heartbeat=now,
    ))
    await db_session.commit()

    # Mock Redis: w1 is online (idle), w2 is not in Redis (offline)
    async def hgetall_side_effect(key: str) -> dict:
        if key == f"worker:{w1_id}":
            return {
                "id": str(w1_id), "name": "W1", "platform": "linux",
                "capabilities": "[]", "executor_type": "claude-code",
                "status": "idle", "current_task_id": "",
            }
        return {}

    mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

    response = await api_client.get("/api/v1/workers")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    by_id = {w["id"]: w for w in data}
    assert by_id[str(w1_id)]["status"] == "idle"
    assert by_id[str(w2_id)]["status"] == "offline"


async def test_list_workers_empty(api_client: AsyncClient, mock_redis: AsyncMock) -> None:
    """GET /api/v1/workers with no DB workers returns empty list."""
    response = await api_client.get("/api/v1/workers")

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


# ── DB upsert on register ───────────────────────────────────────────────


async def test_register_creates_db_worker(
    api_client: AsyncClient, mock_redis: AsyncMock,
    valid_registration_token: str, db_session: AsyncSession,
) -> None:
    """POST /api/workers/register should also create a DB worker row."""
    from sqlalchemy import select

    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "name": "db-test-worker",
            "platform": "linux",
            "capabilities": {"python": True},
            "executor_type": "claude-code",
            "registration_token": valid_registration_token,
        },
    )
    assert response.status_code == 200
    worker_id = response.json()["worker_id"]

    # Verify DB row exists
    result = await db_session.execute(
        select(models.Worker).where(models.Worker.id == uuid.UUID(worker_id))
    )
    db_worker = result.scalar_one_or_none()
    assert db_worker is not None
    assert db_worker.name == "db-test-worker"
    assert db_worker.platform == "linux"
    assert db_worker.project_id is None


async def test_re_register_updates_db_worker(
    api_client: AsyncClient, mock_redis: AsyncMock,
    valid_registration_token: str, db_session: AsyncSession,
) -> None:
    """Re-registering with same worker_id should update existing DB row, not duplicate."""
    from datetime import datetime, timezone
    from sqlalchemy import select

    # Create initial DB worker
    existing_id = uuid.uuid4()
    db_session.add(models.Worker(
        id=existing_id, name="old-name", platform="linux", capabilities=[],
        executor_type="claude-code", status=models.WorkerStatus.idle,
        registered_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    response = await api_client.post(
        "/api/v1/workers/register",
        json={
            "name": "new-name",
            "platform": "darwin",
            "worker_id": str(existing_id),
            "registration_token": valid_registration_token,
        },
    )
    assert response.status_code == 200
    assert response.json()["worker_id"] == str(existing_id)

    # Verify DB row was updated, not duplicated
    result = await db_session.execute(select(models.Worker))
    all_workers = result.scalars().all()
    assert len(all_workers) == 1
    assert all_workers[0].name == "new-name"
    assert all_workers[0].platform == "darwin"
