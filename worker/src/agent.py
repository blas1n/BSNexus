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
        """Register this worker with the server. Reuses existing worker_id if available."""
        name = self.config.worker_name or f"worker-{platform.system().lower()}-{socket.gethostname()}"
        capabilities = self._detect_capabilities()

        payload: dict = {
            "name": name,
            "platform": platform.system().lower(),
            "capabilities": {cap: True for cap in capabilities},
            "executor_type": self.config.executor_type,
            "registration_token": self.config.registration_token or "",
        }

        # Include existing credentials for re-registration (preserves worker_id)
        if self.worker_id:
            payload["worker_id"] = self.worker_id
        if self.token:
            payload["worker_token"] = self.token

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.config.server_url}/api/v1/workers/register",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            self.worker_id = data["worker_id"]
            self.token = data["token"]
            self.streams = data["streams"]
            self.consumer_groups = data["consumer_groups"]

    async def heartbeat_loop(self) -> None:
        """Periodically send heartbeat to the server."""
        consecutive_failures = 0
        while self._running:
            await asyncio.sleep(self.config.heartbeat_interval)
            if not self._running:
                break
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.config.server_url}/api/v1/workers/{self.worker_id}/heartbeat",
                        headers={"Authorization": f"Bearer {self.token}"},
                    )
                    if response.status_code == 404:
                        print("Heartbeat 404: worker expired, re-registering...")
                        await self._re_register()
                    elif response.status_code >= 400:
                        consecutive_failures += 1
                        print(f"Heartbeat error: HTTP {response.status_code} ({consecutive_failures} failures)")
                    else:
                        consecutive_failures = 0
            except Exception as e:
                consecutive_failures += 1
                print(f"Heartbeat failed ({consecutive_failures}): {type(e).__name__}: {e}")
                # Retry once after a short delay
                if consecutive_failures == 1:
                    await asyncio.sleep(5)
                    continue
                # Re-register after 3 consecutive failures
                if consecutive_failures >= 3:
                    print("Too many heartbeat failures, re-registering...")
                    await self._re_register()
                    consecutive_failures = 0

    async def _re_register(self) -> None:
        """Re-register with the server, preserving stream/group info for consumers."""
        try:
            await self.register()
            print(f"Re-registered as worker {self.worker_id}")
        except Exception as e:
            print(f"Re-registration failed: {type(e).__name__}: {e}")

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
