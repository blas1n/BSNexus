import asyncio
import json

import redis.asyncio as redis_lib

from worker.src.agent import WorkerAgent
from worker.src.executors.base import BaseExecutor
from worker.src.git_ops import WorkerGitOps


class TaskConsumer:
    def __init__(self, redis_client: redis_lib.Redis, agent: WorkerAgent, executor: BaseExecutor) -> None:
        self.redis = redis_client
        self.agent = agent
        self.executor = executor

    def _worker_id(self) -> str:
        """Return worker_id, raising if not yet registered."""
        if self.agent.worker_id is None:
            raise RuntimeError("Worker not registered")
        return self.agent.worker_id

    async def task_loop(self) -> None:
        """Consume tasks from the task queue."""
        while self.agent._running:
            try:
                messages = await self.redis.xreadgroup(  # type: ignore[misc]
                    groupname=self.agent.consumer_groups["workers"],
                    consumername=self._worker_id(),
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
                    consumername=self._worker_id(),
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

    @staticmethod
    def _decode(value: str | bytes) -> str:
        """Decode bytes to str if needed."""
        return value.decode() if isinstance(value, bytes) else value

    async def _process_task(self, msg_id: str, data: dict) -> None:
        """Execute a task and publish result."""
        task_id = self._decode(data.get("task_id", ""))
        msg_type = self._decode(data.get("type", "execution"))

        # Handle revert requests
        if msg_type == "revert":
            await self._process_revert(msg_id, data)
            return

        repo_path = self._decode(data.get("repo_path", ""))
        branch_name = self._decode(data.get("branch_name", ""))
        title = self._decode(data.get("title", ""))

        prompt_raw = self._decode(data.get("worker_prompt", "{}"))

        try:
            prompt_data = json.loads(prompt_raw)
            prompt = prompt_data.get("prompt", prompt_raw) if isinstance(prompt_data, dict) else prompt_raw
        except (json.JSONDecodeError, TypeError):
            prompt = prompt_raw

        try:
            # Initialize git repo and branch
            git_ops = None
            if repo_path:
                git_ops = WorkerGitOps(repo_path)
                await git_ops.ensure_repo()
                if branch_name:
                    await git_ops.ensure_branch(branch_name)

            # Execute task in repo directory
            context: dict = {"task_id": task_id}
            if repo_path:
                context["workspace_dir"] = repo_path

            result = await self.executor.execute(prompt, context)

            # Commit if execution succeeded
            commit_hash = ""
            if result.success and git_ops and branch_name:
                try:
                    commit_hash = await git_ops.commit_task(task_id, title, branch_name)
                except RuntimeError:
                    pass  # Git failure should not fail the task

            await self.redis.xadd(  # type: ignore[misc]
                self.agent.streams["tasks_results"],
                {
                    "task_id": task_id,
                    "worker_id": self.agent.worker_id or "",
                    "type": "execution",
                    "success": str(result.success).lower(),
                    "output_path": result.output_path or "",
                    "error_message": result.error_message or "",
                    "commit_hash": commit_hash,
                    "branch_name": branch_name,
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
                    "commit_hash": "",
                    "branch_name": branch_name,
                },
            )
        finally:
            await self.redis.xack(  # type: ignore[misc]
                self.agent.streams["tasks_queue"],
                self.agent.consumer_groups["workers"],
                msg_id,
            )

    async def _process_revert(self, msg_id: str, data: dict) -> None:
        """Handle a revert request from the backend."""
        repo_path = self._decode(data.get("repo_path", ""))
        commit_hash = self._decode(data.get("commit_hash", ""))
        branch_name = self._decode(data.get("branch_name", ""))

        try:
            if repo_path and commit_hash and branch_name:
                git_ops = WorkerGitOps(repo_path)
                await git_ops.revert_task(commit_hash, branch_name)
        except RuntimeError:
            pass  # Revert failure is non-fatal
        finally:
            await self.redis.xack(  # type: ignore[misc]
                self.agent.streams["tasks_queue"],
                self.agent.consumer_groups["workers"],
                msg_id,
            )

    async def _process_qa(self, msg_id: str, data: dict) -> None:
        """Execute a QA review and publish result."""
        task_id = self._decode(data.get("task_id", ""))
        repo_path = self._decode(data.get("repo_path", ""))

        prompt_raw = self._decode(data.get("qa_prompt", "{}"))

        try:
            prompt_data = json.loads(prompt_raw)
            prompt = prompt_data.get("prompt", prompt_raw) if isinstance(prompt_data, dict) else prompt_raw
        except (json.JSONDecodeError, TypeError):
            prompt = prompt_raw

        try:
            context: dict = {"task_id": task_id}
            if repo_path:
                context["workspace_dir"] = repo_path

            result = await self.executor.review(prompt, context)

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
