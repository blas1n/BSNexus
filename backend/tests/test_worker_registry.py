from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.utils.worker_registry import WorkerRegistry


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock Redis client with all methods used by WorkerRegistry."""
    r = AsyncMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.hget = AsyncMock(return_value=None)
    r.expire = AsyncMock()
    r.exists = AsyncMock(return_value=1)
    r.set = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.delete = AsyncMock()

    # scan_iter returns an async iterator
    r.scan_iter = MagicMock(return_value=_async_iter([]))
    return r


@pytest.fixture
def registry(mock_redis: AsyncMock) -> WorkerRegistry:
    return WorkerRegistry(mock_redis, ttl=60)


# ── Helpers ──────────────────────────────────────────────────────────────


async def _async_iter(items: list):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


# ── register ─────────────────────────────────────────────────────────────


async def test_register_creates_redis_hash(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """register() should HSET the worker data and set TTL."""
    result = await registry.register(
        worker_id="w-1",
        name="Worker One",
        platform="linux",
        capabilities=["python", "node"],
        executor_type="claude-code",
    )

    # HSET was called with worker:w-1
    mock_redis.hset.assert_called_once()
    call_kwargs = mock_redis.hset.call_args
    assert call_kwargs[0][0] == "worker:w-1"
    mapping = call_kwargs[1]["mapping"]
    assert mapping["id"] == "w-1"
    assert mapping["name"] == "Worker One"
    assert mapping["platform"] == "linux"
    assert json.loads(mapping["capabilities"]) == ["python", "node"]
    assert mapping["executor_type"] == "claude-code"
    assert mapping["status"] == "idle"

    # EXPIRE 60s on worker hash
    mock_redis.expire.assert_called_once_with("worker:w-1", 60)

    # Token stored: SET worker:token:{token} w-1 EX 86400
    mock_redis.set.assert_called_once()
    set_args = mock_redis.set.call_args
    assert set_args[0][1] == "w-1"  # value is worker_id
    assert set_args[1]["ex"] == 86400

    # Return value
    assert result["worker_id"] == "w-1"
    assert result["token"]  # non-empty
    assert len(result["token"]) == 64  # secrets.token_hex(32) produces 64 chars
    assert result["status"] == "idle"


async def test_register_generates_64_char_token(registry: WorkerRegistry) -> None:
    """Token should be 64 hex characters (secrets.token_hex(32))."""
    with patch("backend.src.utils.worker_registry.secrets.token_hex", return_value="a" * 64) as mock_hex:
        result = await registry.register("w-2", "W2", "linux", [], "claude-code")
        mock_hex.assert_called_once_with(32)
        assert result["token"] == "a" * 64


# ── heartbeat ────────────────────────────────────────────────────────────


async def test_heartbeat_renews_ttl(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """heartbeat() should renew EXPIRE on the worker key."""
    mock_redis.exists.return_value = 1

    alive = await registry.heartbeat("w-1")

    assert alive is True
    mock_redis.expire.assert_called_once_with("worker:w-1", 60)


async def test_heartbeat_returns_false_for_missing_worker(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """heartbeat() returns False when the worker key does not exist."""
    mock_redis.exists.return_value = 0

    alive = await registry.heartbeat("w-missing")

    assert alive is False
    mock_redis.expire.assert_not_called()


# ── get_worker ───────────────────────────────────────────────────────────


async def test_get_worker_returns_info(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """get_worker() should return deserialized worker data."""
    mock_redis.hgetall.return_value = {
        "id": "w-1",
        "name": "Worker One",
        "platform": "linux",
        "capabilities": json.dumps(["python"]),
        "executor_type": "claude-code",
        "status": "idle",
        "current_task_id": "",
    }

    worker = await registry.get_worker("w-1")

    assert worker is not None
    assert worker["id"] == "w-1"
    assert worker["name"] == "Worker One"
    assert worker["capabilities"] == ["python"]
    assert worker["current_task_id"] is None  # empty string → None


async def test_get_worker_returns_none_for_missing(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """get_worker() returns None when the key has expired."""
    mock_redis.hgetall.return_value = {}

    worker = await registry.get_worker("w-gone")

    assert worker is None


# ── get_all_workers ──────────────────────────────────────────────────────


async def test_get_all_workers_returns_active_only(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """get_all_workers() should return workers from SCAN, filtering out token keys."""
    # scan_iter yields both worker keys and token keys
    mock_redis.scan_iter = MagicMock(
        return_value=_async_iter(["worker:w-1", "worker:token:abc123", "worker:w-2"])
    )

    # hgetall returns data for w-1 and w-2
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
                "current_task_id": "task-99",
            }
        return {}

    mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

    workers = await registry.get_all_workers()

    assert len(workers) == 2
    ids = {w["id"] for w in workers}
    assert ids == {"w-1", "w-2"}


async def test_get_all_workers_empty(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """get_all_workers() returns empty list when no workers are registered."""
    mock_redis.scan_iter = MagicMock(return_value=_async_iter([]))

    workers = await registry.get_all_workers()

    assert workers == []


# ── set_busy / set_idle ──────────────────────────────────────────────────


async def test_set_busy_updates_status(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """set_busy() should HSET status=busy and current_task_id."""
    await registry.set_busy("w-1", "task-42")

    mock_redis.hset.assert_called_once_with(
        "worker:w-1",
        mapping={"status": "busy", "current_task_id": "task-42"},
    )


async def test_set_idle_updates_status(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """set_idle() should HSET status=idle and clear current_task_id."""
    await registry.set_idle("w-1")

    mock_redis.hset.assert_called_once_with(
        "worker:w-1",
        mapping={"status": "idle", "current_task_id": ""},
    )


# ── deregister ───────────────────────────────────────────────────────────


async def test_deregister_cleans_up_keys(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """deregister() should delete worker hash and token key."""
    mock_redis.hget.return_value = "my-secret-token"

    await registry.deregister("w-1")

    # Should have looked up the token
    mock_redis.hget.assert_called_once_with("worker:w-1", "token")
    # Should delete worker hash and token key
    assert mock_redis.delete.call_count == 2
    deleted_keys = [call[0][0] for call in mock_redis.delete.call_args_list]
    assert "worker:w-1" in deleted_keys
    assert "worker:token:my-secret-token" in deleted_keys


async def test_deregister_without_token(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """deregister() should only delete worker hash when no token is stored."""
    mock_redis.hget.return_value = None

    await registry.deregister("w-1")

    # Only the worker key should be deleted
    mock_redis.delete.assert_called_once_with("worker:w-1")


# ── resolve_token ────────────────────────────────────────────────────────


async def test_resolve_token_returns_worker_id(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """resolve_token() should return the worker_id for a valid token."""
    mock_redis.get.return_value = "w-1"

    worker_id = await registry.resolve_token("valid-token")

    assert worker_id == "w-1"
    mock_redis.get.assert_called_once_with("worker:token:valid-token")


async def test_resolve_token_returns_none_for_invalid(registry: WorkerRegistry, mock_redis: AsyncMock) -> None:
    """resolve_token() returns None when the token doesn't exist."""
    mock_redis.get.return_value = None

    worker_id = await registry.resolve_token("invalid-token")

    assert worker_id is None
