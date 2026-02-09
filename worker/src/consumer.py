import asyncio
import json

import redis.asyncio as redis_lib

from worker.src.agent import WorkerAgent
from worker.src.executors.base import BaseExecutor


class TaskConsumer:
    def __init__(self, redis_client: redis_lib.Redis, agent: WorkerAgent, executor: BaseExecutor) -> None:
        self.redis = redis_client
        self.agent = agent
        self.executor = executor

    async def task_loop(self) -> None:
        """Consume tasks from the task queue."""
        while self.agent._running:
            try:
                messages = await self.redis.xreadgroup(  # type: ignore[misc]
                    groupname=self.agent.consumer_groups["workers"],
                    consumername=self.agent.worker_id,
                    streams={self.agent.streams["tasks_queue"]: ">"},
                    count=1,
                    block=30000,
                )

                if messages:
                    for stream, entries in messages:
                        for msg_id, data in entries:
                            await self._process_task(msg_id, data)
            except Exception as e:
                if self.agent._running:
                    print(f"Task loop error: {e}")
                    await asyncio.sleep(5)

    async def qa_loop(self) -> None:
        """Consume QA review tasks."""
        while self.agent._running:
            try:
                messages = await self.redis.xreadgroup(  # type: ignore[misc]
                    groupname=self.agent.consumer_groups["reviewers"],
                    consumername=self.agent.worker_id,
                    streams={self.agent.streams["tasks_qa"]: ">"},
                    count=1,
                    block=30000,
                )

                if messages:
                    for stream, entries in messages:
                        for msg_id, data in entries:
                            await self._process_qa(msg_id, data)
            except Exception as e:
                if self.agent._running:
                    print(f"QA loop error: {e}")
                    await asyncio.sleep(5)

    async def _process_task(self, msg_id: str, data: dict) -> None:
        """Execute a task and publish result."""
        task_id = data.get("task_id", "")
        if isinstance(task_id, bytes):
            task_id = task_id.decode()

        prompt_raw = data.get("worker_prompt", "{}")
        if isinstance(prompt_raw, bytes):
            prompt_raw = prompt_raw.decode()

        try:
            prompt_data = json.loads(prompt_raw)
            prompt = prompt_data.get("prompt", prompt_raw) if isinstance(prompt_data, dict) else prompt_raw
        except (json.JSONDecodeError, TypeError):
            prompt = prompt_raw

        try:
            result = await self.executor.execute(prompt, {"task_id": task_id})

            await self.redis.xadd(  # type: ignore[misc]
                self.agent.streams["tasks_results"],
                {
                    "task_id": task_id,
                    "worker_id": self.agent.worker_id or "",
                    "type": "execution",
                    "success": str(result.success).lower(),
                    "output_path": result.output_path or "",
                    "error_message": result.error_message or "",
                },
            )
        except Exception as e:
            await self.redis.xadd(  # type: ignore[misc]
                self.agent.streams["tasks_results"],
                {
                    "task_id": task_id,
                    "worker_id": self.agent.worker_id or "",
                    "type": "execution",
                    "success": "false",
                    "error_message": str(e),
                },
            )
        finally:
            await self.redis.xack(  # type: ignore[misc]
                self.agent.streams["tasks_queue"],
                self.agent.consumer_groups["workers"],
                msg_id,
            )

    async def _process_qa(self, msg_id: str, data: dict) -> None:
        """Execute a QA review and publish result."""
        task_id = data.get("task_id", "")
        if isinstance(task_id, bytes):
            task_id = task_id.decode()

        prompt_raw = data.get("qa_prompt", "{}")
        if isinstance(prompt_raw, bytes):
            prompt_raw = prompt_raw.decode()

        try:
            prompt_data = json.loads(prompt_raw)
            prompt = prompt_data.get("prompt", prompt_raw) if isinstance(prompt_data, dict) else prompt_raw
        except (json.JSONDecodeError, TypeError):
            prompt = prompt_raw

        try:
            result = await self.executor.review(prompt, {"task_id": task_id})

            await self.redis.xadd(  # type: ignore[misc]
                self.agent.streams["tasks_results"],
                {
                    "task_id": task_id,
                    "worker_id": self.agent.worker_id or "",
                    "type": "qa",
                    "passed": str(result.passed).lower(),
                    "feedback": result.feedback,
                    "error_message": result.error_message or "",
                },
            )
        except Exception as e:
            await self.redis.xadd(  # type: ignore[misc]
                self.agent.streams["tasks_results"],
                {
                    "task_id": task_id,
                    "worker_id": self.agent.worker_id or "",
                    "type": "qa",
                    "passed": "false",
                    "feedback": "",
                    "error_message": str(e),
                },
            )
        finally:
            await self.redis.xack(  # type: ignore[misc]
                self.agent.streams["tasks_qa"],
                self.agent.consumer_groups["reviewers"],
                msg_id,
            )
