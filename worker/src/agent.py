import asyncio
import platform
import socket
from pathlib import Path

import httpx

from worker.src.config import WorkerConfig


class WorkerAgent:
    def __init__(self, config: WorkerConfig) -> None:
        self.config = config
        self.worker_id: str | None = None
        self.token: str | None = None
        self.streams: dict[str, str] = {}
        self.consumer_groups: dict[str, str] = {}
        self._running = True

    async def register(self) -> None:
        """Register this worker with the server."""
        name = self.config.worker_name or f"worker-{platform.system().lower()}-{socket.gethostname()}"
        capabilities = self._detect_capabilities()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.config.server_url}/api/v1/workers/register",
                json={
                    "name": name,
                    "platform": platform.system().lower(),
                    "capabilities": {cap: True for cap in capabilities},
                    "executor_type": self.config.executor_type,
                    "registration_token": self.config.registration_token or "",
                },
            )
            response.raise_for_status()

            data = response.json()
            self.worker_id = data["worker_id"]
            self.token = data["token"]
            self.streams = data["streams"]
            self.consumer_groups = data["consumer_groups"]

    async def heartbeat_loop(self) -> None:
        """Periodically send heartbeat to the server."""
        while self._running:
            await asyncio.sleep(self.config.heartbeat_interval)
            if not self._running:
                break
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.config.server_url}/api/v1/workers/{self.worker_id}/heartbeat",
                        headers={"Authorization": f"Bearer {self.token}"},
                    )
                    if response.status_code == 404:
                        await self.register()  # re-register
            except Exception as e:
                print(f"Heartbeat failed: {e}")

    def _detect_capabilities(self) -> list[str]:
        """Detect execution environment capabilities."""
        capabilities: list[str] = []
        # Check for devcontainer
        if Path("/.dockerenv").exists():
            capabilities.append("docker")
        if Path("/workspace/.devcontainer").exists():
            capabilities.append("devcontainer")
        capabilities.append("native")
        return capabilities

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self.worker_id and self.token:
            try:
                async with httpx.AsyncClient() as client:
                    await client.delete(
                        f"{self.config.server_url}/api/v1/workers/{self.worker_id}",
                    )
            except Exception:
                pass
