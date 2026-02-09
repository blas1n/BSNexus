from __future__ import annotations

import json
import secrets

import redis.asyncio as redis


class WorkerRegistry:
    """Redis Hash + TTL based Worker Registry.

    Each worker is stored as a Redis Hash at key ``worker:{id}``.
    An authentication token is stored at ``worker:token:{token}`` pointing to the worker id.
    The worker hash expires after ``ttl`` seconds; heartbeat renews the TTL.
    """

    PREFIX = "worker:"
    TOKEN_PREFIX = "worker:token:"
    TOKEN_TTL = 86400  # 24 hours

    def __init__(self, redis_client: redis.Redis, ttl: int = 60) -> None:
        self.redis = redis_client
        self.ttl = ttl

    # -- helpers ---------------------------------------------------------------

    def _worker_key(self, worker_id: str) -> str:
        return f"{self.PREFIX}{worker_id}"

    def _token_key(self, token: str) -> str:
        return f"{self.TOKEN_PREFIX}{token}"

    # -- public API ------------------------------------------------------------

    async def register(
        self,
        worker_id: str,
        name: str,
        platform: str,
        capabilities: list[str],
        executor_type: str,
    ) -> dict:
        """Register a worker in Redis (Hash + TTL) and create an auth token."""
        token = secrets.token_hex(32)
        key = self._worker_key(worker_id)

        mapping: dict[str, str] = {
            "id": worker_id,
            "name": name,
            "platform": platform,
            "capabilities": json.dumps(capabilities),
            "executor_type": executor_type,
            "status": "idle",
            "current_task_id": "",
            "token": token,
        }

        await self.redis.hset(key, mapping=mapping)  # type: ignore[misc]
        await self.redis.expire(key, self.ttl)  # type: ignore[misc]

        # Store token -> worker_id mapping
        await self.redis.set(self._token_key(token), worker_id, ex=self.TOKEN_TTL)  # type: ignore[misc]

        return {
            "worker_id": worker_id,
            "token": token,
            "name": name,
            "platform": platform,
            "capabilities": capabilities,
            "executor_type": executor_type,
            "status": "idle",
        }

    async def heartbeat(self, worker_id: str) -> bool:
        """Renew the TTL for a worker. Returns True if the worker exists."""
        key = self._worker_key(worker_id)
        exists = await self.redis.exists(key)  # type: ignore[misc]
        if not exists:
            return False
        await self.redis.expire(key, self.ttl)  # type: ignore[misc]
        return True

    async def get_worker(self, worker_id: str) -> dict | None:
        """Return worker info dict, or None if the key has expired / doesn't exist."""
        key = self._worker_key(worker_id)
        data = await self.redis.hgetall(key)  # type: ignore[misc]
        if not data:
            return None

        # Deserialize capabilities from JSON string
        caps_raw = data.get("capabilities", "[]")
        try:
            capabilities = json.loads(caps_raw)
        except (json.JSONDecodeError, TypeError):
            capabilities = []

        return {
            "id": data.get("id", worker_id),
            "name": data.get("name", ""),
            "platform": data.get("platform", ""),
            "capabilities": capabilities,
            "executor_type": data.get("executor_type", "claude-code"),
            "status": data.get("status", "idle"),
            "current_task_id": data.get("current_task_id", "") or None,
        }

    async def get_all_workers(self) -> list[dict]:
        """Return a list of all active (non-expired) workers via SCAN."""
        workers: list[dict] = []
        async for key in self.redis.scan_iter(match=f"{self.PREFIX}*"):
            # Filter out token keys
            if isinstance(key, bytes):
                key = key.decode()
            if key.startswith(self.TOKEN_PREFIX):
                continue

            worker_id = key[len(self.PREFIX):]
            worker = await self.get_worker(worker_id)
            if worker is not None:
                workers.append(worker)

        return workers

    async def set_busy(self, worker_id: str, task_id: str) -> None:
        """Set worker status to busy and record the current task."""
        key = self._worker_key(worker_id)
        await self.redis.hset(key, mapping={"status": "busy", "current_task_id": task_id})  # type: ignore[misc]

    async def set_idle(self, worker_id: str) -> None:
        """Set worker status to idle and clear the current task."""
        key = self._worker_key(worker_id)
        await self.redis.hset(key, mapping={"status": "idle", "current_task_id": ""})  # type: ignore[misc]

    async def deregister(self, worker_id: str) -> None:
        """Remove a worker and its token from Redis."""
        key = self._worker_key(worker_id)

        # Retrieve the token before deleting the worker hash
        token = await self.redis.hget(key, "token")  # type: ignore[misc]
        await self.redis.delete(key)  # type: ignore[misc]

        if token:
            await self.redis.delete(self._token_key(token))  # type: ignore[misc]

    async def resolve_token(self, token: str) -> str | None:
        """Resolve an auth token to a worker_id. Returns None if invalid/expired."""
        worker_id = await self.redis.get(self._token_key(token))  # type: ignore[misc]
        if worker_id is None:
            return None
        if isinstance(worker_id, bytes):
            worker_id = worker_id.decode()
        return worker_id
