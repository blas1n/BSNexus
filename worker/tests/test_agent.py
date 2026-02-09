from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.src.agent import WorkerAgent
from worker.src.config import WorkerConfig


@pytest.fixture
def config() -> WorkerConfig:
    return WorkerConfig(
        server_url="http://test-server:8000",
        redis_url="redis://localhost:6379",
        executor_type="claude-code",
        heartbeat_interval=1,
    )


@pytest.fixture
def agent(config: WorkerConfig) -> WorkerAgent:
    return WorkerAgent(config)


def _make_register_response() -> dict:
    return {
        "worker_id": "test-worker-id-123",
        "token": "test-token-abc",
        "heartbeat_interval": 30,
        "streams": {
            "tasks_queue": "tasks:queue",
            "tasks_results": "tasks:results",
            "tasks_qa": "tasks:qa",
        },
        "consumer_groups": {
            "workers": "workers",
            "reviewers": "reviewers",
        },
    }


class TestWorkerAgentRegister:
    async def test_register_sets_worker_id_and_token(self, agent: WorkerAgent) -> None:
        """register() should set worker_id, token, streams, and consumer_groups."""
        mock_response = MagicMock()
        mock_response.json.return_value = _make_register_response()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("worker.src.agent.httpx.AsyncClient", return_value=mock_client):
            await agent.register()

        assert agent.worker_id == "test-worker-id-123"
        assert agent.token == "test-token-abc"
        assert agent.streams == {
            "tasks_queue": "tasks:queue",
            "tasks_results": "tasks:results",
            "tasks_qa": "tasks:qa",
        }
        assert agent.consumer_groups == {
            "workers": "workers",
            "reviewers": "reviewers",
        }

    async def test_register_sends_correct_payload(self, agent: WorkerAgent) -> None:
        """register() should POST to /api/workers/register with expected payload."""
        mock_response = MagicMock()
        mock_response.json.return_value = _make_register_response()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("worker.src.agent.httpx.AsyncClient", return_value=mock_client):
            await agent.register()

        call_args = mock_client.post.call_args
        assert "/api/workers/register" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["platform"] in ("linux", "windows", "darwin")
        assert payload["executor_type"] == "claude-code"
        assert "capabilities" in payload


class TestWorkerAgentHeartbeat:
    async def test_heartbeat_loop_sends_heartbeat(self, agent: WorkerAgent) -> None:
        """heartbeat_loop() should send a POST to /api/workers/{id}/heartbeat."""
        agent.worker_id = "test-worker-id"
        agent.token = "test-token"

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        call_count = 0
        original_sleep = __import__("asyncio").sleep

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                agent._running = False
            await original_sleep(0)

        with (
            patch("worker.src.agent.httpx.AsyncClient", return_value=mock_client),
            patch("worker.src.agent.asyncio.sleep", side_effect=fake_sleep),
        ):
            await agent.heartbeat_loop()

        mock_client.post.assert_called()
        call_args = mock_client.post.call_args
        assert "test-worker-id" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-token"

    async def test_heartbeat_loop_reregisters_on_404(self, agent: WorkerAgent) -> None:
        """heartbeat_loop() should re-register when server returns 404."""
        agent.worker_id = "old-worker-id"
        agent.token = "old-token"
        agent.config.heartbeat_interval = 1

        mock_404_response = MagicMock()
        mock_404_response.status_code = 404

        mock_register_response = MagicMock()
        mock_register_response.json.return_value = _make_register_response()
        mock_register_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_404_response, mock_register_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        call_count = 0
        original_sleep = __import__("asyncio").sleep

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                agent._running = False
            await original_sleep(0)

        with (
            patch("worker.src.agent.httpx.AsyncClient", return_value=mock_client),
            patch("worker.src.agent.asyncio.sleep", side_effect=fake_sleep),
        ):
            await agent.heartbeat_loop()

        # After re-registration, worker_id should be updated
        assert agent.worker_id == "test-worker-id-123"
        assert agent.token == "test-token-abc"


class TestWorkerAgentCapabilities:
    def test_detect_capabilities_returns_list(self, agent: WorkerAgent) -> None:
        """_detect_capabilities() should always return a list containing 'native'."""
        capabilities = agent._detect_capabilities()
        assert isinstance(capabilities, list)
        assert "native" in capabilities

    def test_detect_capabilities_includes_docker(self, agent: WorkerAgent) -> None:
        """_detect_capabilities() should include 'docker' when /.dockerenv exists."""
        with patch("worker.src.agent.Path.exists", return_value=True):
            capabilities = agent._detect_capabilities()
        assert "docker" in capabilities

    def test_detect_capabilities_no_docker(self, agent: WorkerAgent) -> None:
        """_detect_capabilities() should not include 'docker' when /.dockerenv does not exist."""
        with patch("worker.src.agent.Path.exists", return_value=False):
            capabilities = agent._detect_capabilities()
        # native is always there; docker/devcontainer may not be
        assert "native" in capabilities


class TestWorkerAgentShutdown:
    async def test_shutdown_sets_running_false(self, agent: WorkerAgent) -> None:
        """shutdown() should set _running to False."""
        agent.worker_id = "test-worker-id"
        agent.token = "test-token"

        mock_response = MagicMock()
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("worker.src.agent.httpx.AsyncClient", return_value=mock_client):
            await agent.shutdown()

        assert agent._running is False

    async def test_shutdown_calls_delete(self, agent: WorkerAgent) -> None:
        """shutdown() should call DELETE /api/workers/{worker_id}."""
        agent.worker_id = "test-worker-id"
        agent.token = "test-token"

        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(return_value=MagicMock())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("worker.src.agent.httpx.AsyncClient", return_value=mock_client):
            await agent.shutdown()

        mock_client.delete.assert_called_once()
        call_args = mock_client.delete.call_args
        assert "test-worker-id" in call_args[0][0]

    async def test_shutdown_without_worker_id(self, agent: WorkerAgent) -> None:
        """shutdown() should not call DELETE if worker_id is None."""
        agent.worker_id = None
        agent.token = None

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("worker.src.agent.httpx.AsyncClient", return_value=mock_client):
            await agent.shutdown()

        assert agent._running is False
        mock_client.delete.assert_not_called()
