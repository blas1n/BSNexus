import asyncio
import json
import time

from worker.agent import WorkerAgent
from worker.executors.base import BaseExecutor
from worker.git_ops import WorkerGitOps
from worker.log import log


class TaskConsumer:
    def __init__(self, agent: WorkerAgent, executor: BaseExecutor) -> None:
        self.agent = agent
        self.executor = executor

    async def poll_loop(self) -> None:
        """Unified poll loop: fetches tasks/QA/reverts from the backend via HTTP."""
        log.info("Poll loop started (interval=%ds)", self.agent.config.poll_interval)

        while self.agent._running:
            try:
                items = await self.agent.poll()

                for item in items:
                    msg_type = item.get("type", "task")
                    msg_id = item.get("message_id", "")
                    stream = item.get("stream", "task")
                    data = item.get("data", {})

                    if msg_type == "revert":
                        await self._process_revert(msg_id, stream, data)
                    elif msg_type == "qa" or stream == "qa":
                        await self._process_qa(msg_id, stream, data)
                    else:
                        await self._process_task(msg_id, stream, data)

                if not items:
                    await asyncio.sleep(self.agent.config.poll_interval)

            except Exception as e:
                if self.agent._running:
                    log.error("Poll loop error: %s: %s", type(e).__name__, e)
                    await asyncio.sleep(5)

    @staticmethod
    def _extract_prompt(data: dict, key: str) -> str:
        """Extract prompt string from a data dict field (may be JSON-encoded or plain string)."""
        prompt_raw = data.get(key, "{}")
        if isinstance(prompt_raw, dict):
            return prompt_raw.get("prompt", str(prompt_raw))
        prompt_raw = str(prompt_raw)
        try:
            prompt_data = json.loads(prompt_raw)
            return prompt_data.get("prompt", prompt_raw) if isinstance(prompt_data, dict) else prompt_raw
        except (json.JSONDecodeError, TypeError):
            return prompt_raw

    async def _process_task(self, msg_id: str, stream: str, data: dict) -> None:
        """Execute a task and submit result via HTTP."""
        task_id = str(data.get("task_id", ""))
        repo_path = str(data.get("repo_path", ""))
        branch_name = str(data.get("branch_name", ""))
        title = str(data.get("title", ""))

        log.info(">>> TASK RECEIVED  task_id=%s title='%s'", task_id, title)
        log.info("    repo=%s branch=%s", repo_path or "(none)", branch_name or "(none)")

        prompt = self._extract_prompt(data, "worker_prompt")

        # Inject retry feedback from previous failed attempt
        retry_feedback = str(data.get("retry_feedback", ""))
        retry_count = str(data.get("retry_count", "0"))
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
            git_ops = None
            if repo_path:
                git_ops = WorkerGitOps(repo_path)
                await git_ops.ensure_repo()
                if branch_name:
                    await git_ops.ensure_branch(branch_name)
                    log.info("    git: checked out branch %s", branch_name)

            context: dict = {"task_id": task_id}
            if repo_path:
                context["workspace_dir"] = repo_path

            log.info("    executing via %s ...", type(self.executor).__name__)
            result = await self.executor.execute(prompt, context)
            elapsed = time.monotonic() - t0

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

            await self.agent.submit_result({
                "message_id": msg_id,
                "stream": stream,
                "result_type": "execution",
                "task_id": task_id,
                "success": result.success,
                "output_path": result.output_path or "",
                "error_message": result.error_message or "",
                "commit_hash": commit_hash,
                "branch_name": branch_name,
            })
        except Exception as e:
            elapsed = time.monotonic() - t0
            log.error("<<< TASK FAILED    task_id=%s elapsed=%.1fs error=%s", task_id, elapsed, e)
            await self.agent.submit_result({
                "message_id": msg_id,
                "stream": stream,
                "result_type": "execution",
                "task_id": task_id,
                "success": False,
                "error_message": str(e),
                "commit_hash": "",
                "branch_name": branch_name,
            })

    async def _process_revert(self, msg_id: str, stream: str, data: dict) -> None:
        """Revert a previously committed task."""
        task_id = str(data.get("task_id", ""))
        repo_path = str(data.get("repo_path", ""))
        commit_hash = str(data.get("commit_hash", ""))
        branch_name = str(data.get("branch_name", ""))

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
            await self.agent.submit_result({
                "message_id": msg_id,
                "stream": stream,
                "result_type": "revert",
                "task_id": task_id,
            })

    async def _process_qa(self, msg_id: str, stream: str, data: dict) -> None:
        """Execute a QA review and submit result via HTTP."""
        task_id = str(data.get("task_id", ""))
        repo_path = str(data.get("repo_path", ""))

        log.info(">>> QA RECEIVED    task_id=%s repo=%s", task_id, repo_path or "(none)")

        prompt = self._extract_prompt(data, "qa_prompt")

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

            await self.agent.submit_result({
                "message_id": msg_id,
                "stream": stream,
                "result_type": "qa",
                "task_id": task_id,
                "passed": result.passed,
                "feedback": result.feedback,
                "error_message": result.error_message or "",
            })
        except Exception as e:
            elapsed = time.monotonic() - t0
            log.error("<<< QA FAILED      task_id=%s elapsed=%.1fs error=%s", task_id, elapsed, e)
            await self.agent.submit_result({
                "message_id": msg_id,
                "stream": stream,
                "result_type": "qa",
                "task_id": task_id,
                "passed": False,
                "feedback": "",
                "error_message": str(e),
            })
