"""Tests for worker poll and result submission endpoints."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src import models
from backend.src.main import app
from backend.src.storage.database import get_db


def _async_iter(items: list):
    """Helper to create an async iterator from a list."""
    async def _gen():
        for item in items:
            yield item
    return _gen()


async def _register_worker(api_client: AsyncClient, token_str: str) -> dict:
    """Helper: register a worker and return the response data."""
    resp = await api_client.post(
        "/api/v1/workers/register",
        json={
            "platform": "linux",
            "capabilities": {"python": True},
            "executor_type": "claude-code",
            "registration_token": token_str,
        },
    )
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
async def setup(db_session: AsyncSession):
    """Set up DB token, mock Redis, mock stream manager, and return test context."""
    token_str = f"glrt-poll-test-{uuid.uuid4().hex[:8]}"
    reg_token = models.RegistrationToken(
        id=uuid.uuid4(),
        token=token_str,
        name="poll-test-token",
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
    mock_redis.xreadgroup = AsyncMock(return_value=[])

    mock_stream_manager = AsyncMock()
    mock_stream_manager.publish = AsyncMock(return_value="mock-msg-id")
    mock_stream_manager.acknowledge = AsyncMock()

    app.state.redis = mock_redis
    app.state.stream_manager = mock_stream_manager

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    yield {
        "token_str": token_str,
        "mock_redis": mock_redis,
        "mock_stream_manager": mock_stream_manager,
    }

    app.dependency_overrides.clear()


class TestPollEndpoint:
    async def test_poll_returns_empty_when_no_work(self, setup: dict) -> None:
        """Poll should return empty items when no messages are available."""
        ctx = setup
        mock_redis = ctx["mock_redis"]
        mock_redis.xreadgroup = AsyncMock(return_value=[])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            worker_id, token = data["worker_id"], data["token"]

            # Resolve token for auth
            mock_redis.get = AsyncMock(return_value=worker_id)

            resp = await client.post(
                f"/api/v1/workers/{worker_id}/poll",
                headers={"Authorization": f"Bearer {token}"},
                json={"poll_types": ["task", "qa"]},
            )

        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_poll_returns_pending_messages_first(self, setup: dict) -> None:
        """Poll should return pending (unacked) messages before polling for new ones."""
        ctx = setup
        mock_redis = ctx["mock_redis"]

        pending_entry = [
            ("tasks:queue", [("msg-001", {"task_id": "t1", "title": "Test Task", "worker_prompt": "do stuff"})])
        ]
        # First call (pending with "0") returns messages; second call (new with ">") should not be reached
        mock_redis.xreadgroup = AsyncMock(side_effect=[pending_entry, []])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            worker_id, token = data["worker_id"], data["token"]
            mock_redis.get = AsyncMock(return_value=worker_id)

            resp = await client.post(
                f"/api/v1/workers/{worker_id}/poll",
                headers={"Authorization": f"Bearer {token}"},
                json={"poll_types": ["task"]},
            )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["message_id"] == "msg-001"
        assert items[0]["stream"] == "task"
        assert items[0]["data"]["task_id"] == "t1"

    async def test_poll_returns_new_messages_when_no_pending(self, setup: dict) -> None:
        """Poll should return new messages when no pending messages exist."""
        ctx = setup
        mock_redis = ctx["mock_redis"]

        new_entry = [
            ("tasks:queue", [("msg-002", {"task_id": "t2", "title": "New Task", "worker_prompt": "code"})])
        ]
        # Pending calls return empty for both task and qa, then new call returns a message
        mock_redis.xreadgroup = AsyncMock(side_effect=[[], [], new_entry])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            worker_id, token = data["worker_id"], data["token"]
            mock_redis.get = AsyncMock(return_value=worker_id)

            resp = await client.post(
                f"/api/v1/workers/{worker_id}/poll",
                headers={"Authorization": f"Bearer {token}"},
                json={"poll_types": ["task", "qa"]},
            )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["data"]["task_id"] == "t2"

    async def test_poll_returns_revert_type(self, setup: dict) -> None:
        """Poll should detect type=revert from message data."""
        ctx = setup
        mock_redis = ctx["mock_redis"]

        revert_entry = [
            ("tasks:queue", [(
                "msg-rev",
                {"type": "revert", "task_id": "t3", "commit_hash": "abc123", "repo_path": "/repo", "branch_name": "b"},
            )])
        ]
        mock_redis.xreadgroup = AsyncMock(side_effect=[revert_entry, []])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            worker_id, token = data["worker_id"], data["token"]
            mock_redis.get = AsyncMock(return_value=worker_id)

            resp = await client.post(
                f"/api/v1/workers/{worker_id}/poll",
                headers={"Authorization": f"Bearer {token}"},
                json={"poll_types": ["task"]},
            )

        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["type"] == "revert"
        assert items[0]["data"]["commit_hash"] == "abc123"

    async def test_poll_rejects_wrong_worker(self, setup: dict) -> None:
        """Poll should return 403 when token doesn't match worker_id."""
        ctx = setup
        mock_redis = ctx["mock_redis"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            token = data["token"]
            # Resolve token to a different worker_id
            mock_redis.get = AsyncMock(return_value="different-worker-id")

            resp = await client.post(
                f"/api/v1/workers/{data['worker_id']}/poll",
                headers={"Authorization": f"Bearer {token}"},
                json={"poll_types": ["task"]},
            )

        assert resp.status_code == 403

    async def test_poll_rejects_missing_auth(self, setup: dict) -> None:
        """Poll should return 401 without auth header."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/workers/{uuid.uuid4()}/poll",
                json={"poll_types": ["task"]},
            )

        assert resp.status_code == 401


class TestSubmitResultEndpoint:
    async def test_submit_execution_result(self, setup: dict) -> None:
        """Submit execution result should publish to tasks:results and ACK."""
        ctx = setup
        mock_redis = ctx["mock_redis"]
        mock_sm = ctx["mock_stream_manager"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            worker_id, token = data["worker_id"], data["token"]
            mock_redis.get = AsyncMock(return_value=worker_id)

            resp = await client.post(
                f"/api/v1/workers/{worker_id}/result",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "message_id": "msg-001",
                    "stream": "task",
                    "result_type": "execution",
                    "task_id": "t1",
                    "success": True,
                    "commit_hash": "abc123",
                    "branch_name": "feat/test",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True

        # Verify publish was called with execution result
        mock_sm.publish.assert_called_once()
        call_args = mock_sm.publish.call_args
        assert call_args[0][0] == "tasks:results"
        published = call_args[0][1]
        assert published["task_id"] == "t1"
        assert published["type"] == "execution"
        assert published["success"] == "true"
        assert published["commit_hash"] == "abc123"

        # Verify ACK was called
        mock_sm.acknowledge.assert_called_once_with("tasks:queue", "workers", "msg-001")

    async def test_submit_qa_result(self, setup: dict) -> None:
        """Submit QA result should publish qa type to tasks:results."""
        ctx = setup
        mock_redis = ctx["mock_redis"]
        mock_sm = ctx["mock_stream_manager"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            worker_id, token = data["worker_id"], data["token"]
            mock_redis.get = AsyncMock(return_value=worker_id)

            resp = await client.post(
                f"/api/v1/workers/{worker_id}/result",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "message_id": "msg-qa-1",
                    "stream": "qa",
                    "result_type": "qa",
                    "task_id": "t2",
                    "passed": False,
                    "feedback": "Missing error handling",
                },
            )

        assert resp.status_code == 200
        published = mock_sm.publish.call_args[0][1]
        assert published["type"] == "qa"
        assert published["passed"] == "false"
        assert published["feedback"] == "Missing error handling"

        # ACK should be on tasks:qa stream
        mock_sm.acknowledge.assert_called_once_with("tasks:qa", "reviewers", "msg-qa-1")

    async def test_submit_revert_result_only_acks(self, setup: dict) -> None:
        """Submit revert result should ACK without publishing to tasks:results."""
        ctx = setup
        mock_redis = ctx["mock_redis"]
        mock_sm = ctx["mock_stream_manager"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            worker_id, token = data["worker_id"], data["token"]
            mock_redis.get = AsyncMock(return_value=worker_id)

            resp = await client.post(
                f"/api/v1/workers/{worker_id}/result",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "message_id": "msg-rev-1",
                    "stream": "task",
                    "result_type": "revert",
                    "task_id": "t3",
                },
            )

        assert resp.status_code == 200
        # Revert should NOT publish to tasks:results
        mock_sm.publish.assert_not_called()
        # But should still ACK
        mock_sm.acknowledge.assert_called_once_with("tasks:queue", "workers", "msg-rev-1")

    async def test_submit_result_rejects_wrong_worker(self, setup: dict) -> None:
        """Submit result should return 403 when token doesn't match worker_id."""
        ctx = setup
        mock_redis = ctx["mock_redis"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            token = data["token"]
            mock_redis.get = AsyncMock(return_value="wrong-worker")

            resp = await client.post(
                f"/api/v1/workers/{data['worker_id']}/result",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "message_id": "msg-x",
                    "stream": "task",
                    "result_type": "execution",
                    "task_id": "tx",
                },
            )

        assert resp.status_code == 403

    async def test_submit_execution_failure_result(self, setup: dict) -> None:
        """Submit execution failure should publish success=false with error message."""
        ctx = setup
        mock_redis = ctx["mock_redis"]
        mock_sm = ctx["mock_stream_manager"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _register_worker(client, ctx["token_str"])
            worker_id, token = data["worker_id"], data["token"]
            mock_redis.get = AsyncMock(return_value=worker_id)

            resp = await client.post(
                f"/api/v1/workers/{worker_id}/result",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "message_id": "msg-fail",
                    "stream": "task",
                    "result_type": "execution",
                    "task_id": "t-fail",
                    "success": False,
                    "error_message": "Compilation error",
                },
            )

        assert resp.status_code == 200
        published = mock_sm.publish.call_args[0][1]
        assert published["success"] == "false"
        assert published["error_message"] == "Compilation error"
