import asyncio
import json
import time

import redis.asyncio as redis_lib

from worker.agent import WorkerAgent
from worker.executors.base import BaseExecutor
from worker.git_ops import WorkerGitOps
from worker.log import log


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
        """Consume tasks from the task queue. Recovers pending messages on startup."""
        stream = self.agent.streams["tasks_queue"]
        group = self.agent.consumer_groups["workers"]
        log.info("Task loop started  stream=%s group=%s", stream, group)

        # Recover any pending messages from a previous crash/restart
        await self._recover_pending(stream, group)

        while self.agent._running:
            try:
                messages = await self.redis.xreadgroup(  # type: ignore[misc]
                    groupname=group,
                    consumername=self._worker_id(),
                    streams={stream: ">"},
                    count=1,
                    block=30000,
                )

                if messages:
                    for _stream, entries in messages:
                        for msg_id, data in entries:
                            await self._process_task(msg_id, data)
            except Exception as e:
                if self.agent._running:
                    log.error("Task loop error: %s", e)
                    await asyncio.sleep(5)

    async def qa_loop(self) -> None:
        """Consume QA review tasks. Recovers pending messages on startup."""
        stream = self.agent.streams["tasks_qa"]
        group = self.agent.consumer_groups["reviewers"]
        log.info("QA loop started    stream=%s group=%s", stream, group)

        await self._recover_pending(stream, group)

        while self.agent._running:
            try:
                messages = await self.redis.xreadgroup(  # type: ignore[misc]
                    groupname=group,
                    consumername=self._worker_id(),
                    streams={stream: ">"},
                    count=1,
                    block=30000,
                )

                if messages:
                    for _stream, entries in messages:
                        for msg_id, data in entries:
                            await self._process_qa(msg_id, data)
            except Exception as e:
                if self.agent._running:
                    log.error("QA loop error: %s", e)
                    await asyncio.sleep(5)

    async def _recover_pending(self, stream: str, group: str) -> None:
        """Re-read and process any pending messages left from a previous crash."""
        try:
            messages = await self.redis.xreadgroup(  # type: ignore[misc]
                groupname=group,
                consumername=self._worker_id(),
                streams={stream: "0"},
                count=10,
            )
            if messages:
                for _stream_name, entries in messages:
                    if entries:
                        log.info("Recovering %d pending message(s) from %s", len(entries), stream)
                    for msg_id, data in entries:
                        if stream == self.agent.streams.get("tasks_qa"):
                            await self._process_qa(msg_id, data)
                        else:
                            await self._process_task(msg_id, data)
        except Exception as e:
            log.error("Pending recovery error on %s: %s", stream, e)

    @staticmethod
    def _decode(value: str | bytes) -> str:
        """Decode bytes to str if needed."""
        return value.decode() if isinstance(value, bytes) else value

    async def _process_task(self, msg_id: str, data: dict) -> None:
        """Execute a task and publish result. Dispatches revert messages separately."""
        msg_type = self._decode(data.get("type", ""))
        if msg_type == "revert":
            await self._process_revert(msg_id, data)
            return

        task_id = self._decode(data.get("task_id", ""))

        repo_path = self._decode(data.get("repo_path", ""))
        branch_name = self._decode(data.get("branch_name", ""))
        title = self._decode(data.get("title", ""))

        log.info(">>> TASK RECEIVED  task_id=%s title='%s'", task_id, title)
        log.info("    repo=%s branch=%s", repo_path or "(none)", branch_name or "(none)")

        prompt_raw = self._decode(data.get("worker_prompt", "{}"))

        try:
            prompt_data = json.loads(prompt_raw)
            prompt = prompt_data.get("prompt", prompt_raw) if isinstance(prompt_data, dict) else prompt_raw
        except (json.JSONDecodeError, TypeError):
            prompt = prompt_raw

        # Inject retry feedback from previous failed attempt
        retry_feedback = self._decode(data.get("retry_feedback", ""))
        retry_count = self._decode(data.get("retry_count", "0"))
        if retry_feedback:
            prompt = (
                f"PREVIOUS ATTEMPT FAILED (attempt {retry_count}).\n"
                f"Feedback from previous attempt:\n{retry_feedback}\n\n"
                f"Please fix the issues identified above and complete the task.\n\n"
                f"Original task:\n{prompt}"
            )

        prompt_preview = prompt[:200].replace("\n", " ")
        log.info("    prompt: %s%s", prompt_preview, "..." if len(prompt) > 200 else "")

        t0 = time.monotonic()
        try:
            # Initialize git repo and branch
            git_ops = None
            if repo_path:
                git_ops = WorkerGitOps(repo_path)
                await git_ops.ensure_repo()
                if branch_name:
                    await git_ops.ensure_branch(branch_name)
                    log.info("    git: checked out branch %s", branch_name)

            # Execute task in repo directory
            context: dict = {"task_id": task_id}
            if repo_path:
                context["workspace_dir"] = repo_path

            log.info("    executing via %s ...", type(self.executor).__name__)
            result = await self.executor.execute(prompt, context)
            elapsed = time.monotonic() - t0

            # Commit if execution succeeded
            commit_hash = ""
            if result.success and git_ops and branch_name:
                try:
                    commit_hash = await git_ops.commit_task(task_id, title, branch_name)
                    log.info("    git: committed %s", commit_hash[:8] if commit_hash else "(no changes)")
                except RuntimeError:
                    log.warning("    git: commit failed (non-fatal)")

            if result.success:
                log.info("<<< TASK DONE      task_id=%s success=true  elapsed=%.1fs", task_id, elapsed)
            else:
                log.warning("<<< TASK DONE      task_id=%s success=false elapsed=%.1fs error=%s",
                            task_id, elapsed, result.error_message or "(unknown)")

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
            elapsed = time.monotonic() - t0
            log.error("<<< TASK FAILED    task_id=%s elapsed=%.1fs error=%s", task_id, elapsed, e)
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
        """Revert a previously committed task."""
        task_id = self._decode(data.get("task_id", ""))
        repo_path = self._decode(data.get("repo_path", ""))
        commit_hash = self._decode(data.get("commit_hash", ""))
        branch_name = self._decode(data.get("branch_name", ""))

        log.info(">>> REVERT RECEIVED task_id=%s commit=%s", task_id, commit_hash or "(none)")

        try:
            if repo_path and commit_hash and branch_name:
                git_ops = WorkerGitOps(repo_path)
                await git_ops.revert_task(commit_hash, branch_name)
                log.info("<<< REVERT DONE    task_id=%s", task_id)
            else:
                log.warning("<<< REVERT SKIPPED task_id=%s (missing repo_path/commit_hash/branch_name)", task_id)
        except Exception as e:
            log.error("<<< REVERT FAILED  task_id=%s error=%s", task_id, e)
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

        log.info(">>> QA RECEIVED    task_id=%s repo=%s", task_id, repo_path or "(none)")

        prompt_raw = self._decode(data.get("qa_prompt", "{}"))

        try:
            prompt_data = json.loads(prompt_raw)
            prompt = prompt_data.get("prompt", prompt_raw) if isinstance(prompt_data, dict) else prompt_raw
        except (json.JSONDecodeError, TypeError):
            prompt = prompt_raw

        t0 = time.monotonic()
        try:
            context: dict = {"task_id": task_id}
            if repo_path:
                context["workspace_dir"] = repo_path

            log.info("    reviewing via %s ...", type(self.executor).__name__)
            result = await self.executor.review(prompt, context)
            elapsed = time.monotonic() - t0

            if result.passed:
                log.info("<<< QA DONE        task_id=%s passed=true  elapsed=%.1fs", task_id, elapsed)
            else:
                feedback_preview = (result.feedback[:120].replace("\n", " ")) if result.feedback else ""
                log.warning("<<< QA DONE        task_id=%s passed=false elapsed=%.1fs feedback=%s",
                            task_id, elapsed, feedback_preview)

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
            elapsed = time.monotonic() - t0
            log.error("<<< QA FAILED      task_id=%s elapsed=%.1fs error=%s", task_id, elapsed, e)
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
