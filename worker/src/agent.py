import asyncio
import platform
import socket
from pathlib import Path

import httpx

from worker.config import WorkerConfig
from worker.log import log


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

        reuse = bool(self.worker_id)
        log.info("Registering worker name=%s reuse_id=%s capabilities=%s", name, reuse, capabilities)

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

        log.info("Registered worker_id=%s streams=%s", self.worker_id, list(self.streams.keys()))

    async def heartbeat_loop(self) -> None:
        """Periodically send heartbeat to the server."""
        consecutive_failures = 0
        log.debug("Heartbeat loop started (interval=%ds)", self.config.heartbeat_interval)
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
                        log.warning("Heartbeat 404: worker expired, re-registering...")
                        await self._re_register()
                    elif response.status_code >= 400:
                        consecutive_failures += 1
                        log.warning("Heartbeat error: HTTP %d (%d failures)", response.status_code, consecutive_failures)
                    else:
                        consecutive_failures = 0
            except Exception as e:
                consecutive_failures += 1
                log.warning("Heartbeat failed (%d): %s: %s", consecutive_failures, type(e).__name__, e)
                # Retry once after a short delay
                if consecutive_failures == 1:
                    await asyncio.sleep(5)
                    continue
                # Re-register after 3 consecutive failures
                if consecutive_failures >= 3:
                    log.error("Too many heartbeat failures, re-registering...")
                    await self._re_register()
                    consecutive_failures = 0

    async def _re_register(self) -> None:
        """Re-register with the server, preserving stream/group info for consumers."""
        try:
            await self.register()
            log.info("Re-registered as worker %s", self.worker_id)
        except Exception as e:
            log.error("Re-registration failed: %s: %s", type(e).__name__, e)

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
        log.info("Shutting down worker %s...", self.worker_id)
        self._running = False
        if self.worker_id and self.token:
            try:
                async with httpx.AsyncClient() as client:
                    await client.delete(
                        f"{self.config.server_url}/api/v1/workers/{self.worker_id}",
                    )
                log.info("Worker unregistered from server")
            except Exception:
                log.warning("Failed to unregister worker from server")
