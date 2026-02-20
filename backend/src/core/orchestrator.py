from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.config import settings
from backend.src.core.llm_client import LLMError, create_llm_client_from_project
from backend.src.core.state_machine import TaskStateMachine
from backend.src.models import PhaseStatus, Task, TaskPriority, TaskStatus
from backend.src.prompts.loader import get_prompt
from backend.src.queue.streams import RedisStreamManager
from backend.src.repositories.phase_repository import PhaseRepository
from backend.src.repositories.project_repository import ProjectRepository
from backend.src.repositories.task_repository import TaskRepository
from backend.src.utils.worker_registry import WorkerRegistry

logger = logging.getLogger(__name__)


class PMOrchestrator:
    """PM Orchestrator - task scheduling, result processing, and auto-retry."""

    def __init__(
        self,
        stream_manager: RedisStreamManager,
        worker_registry: WorkerRegistry,
        state_machine: TaskStateMachine,
    ) -> None:
        self.stream_manager = stream_manager
        self.registry = worker_registry
        self.state_machine = state_machine
        self._running = False

    async def start(self, project_id: uuid.UUID, db_session_factory: Any) -> None:
        """Start orchestration for a project."""
        self._running = True
        # Promote dependency-free waiting tasks before entering the main loops
        await self._promote_waiting_tasks(project_id, db_session_factory)
        await asyncio.gather(
            self._scheduling_loop(project_id, db_session_factory),
            self._results_loop(project_id, db_session_factory),
            self._escalation_loop(project_id, db_session_factory),
        )

    async def _promote_waiting_tasks(self, project_id: uuid.UUID, db_session_factory: Any) -> None:
        """Promote WAITING tasks in the active phase whose dependencies are all met to READY."""
        try:
            async with db_session_factory() as db:
                await self._promote_waiting_tasks_inner(project_id, db)
                await db.commit()
        except Exception:
            logger.exception("Promote waiting tasks error")

    async def _promote_waiting_tasks_inner(self, project_id: uuid.UUID, db: AsyncSession) -> None:
        """Promote WAITING tasks in the active phase (uses existing db session)."""
        phase_repo = PhaseRepository(db)
        task_repo = TaskRepository(db)

        active_phase = await phase_repo.get_active_phase(project_id)
        if active_phase is None:
            first_pending = await phase_repo.get_first_pending_phase(project_id)
            if first_pending is None:
                return
            first_pending.status = PhaseStatus.active
            active_phase = first_pending

        waiting_tasks = await task_repo.list_waiting_in_phase(active_phase.id)
        for task in waiting_tasks:
            if await task_repo.check_dependencies_met(task.id):
                await self.state_machine.transition(
                    task=task,
                    new_status=TaskStatus.ready,
                    reason="All dependencies met",
                    actor="system",
                    db_session=db,
                    stream_manager=self.stream_manager,
                )

    async def stop(self) -> None:
        """Stop orchestration."""
        self._running = False

    async def _scheduling_loop(self, project_id: uuid.UUID, db_session_factory: Any) -> None:
        """Schedule READY tasks one at a time per project (sequential execution)."""
        while self._running:
            try:
                async with db_session_factory() as db:
                    repo = TaskRepository(db)

                    # Sequential constraint: only one task at a time per project
                    active_count = await repo.count_active_tasks(project_id)
                    if active_count > 0:
                        # Release DB connection before sleeping
                        pass
                    else:
                        # Check phase completion and advance to next phase if needed
                        phase_events = await self._check_and_advance_phase(project_id, db)

                        # Promote waiting tasks in the active phase
                        await self._promote_waiting_tasks_inner(project_id, db)

                        ready_tasks = await repo.list_ready_by_priority(project_id)
                        workers = await self.registry.get_all_workers()
                        idle_workers = [w for w in workers if w["status"] == "idle"]

                        if ready_tasks and idle_workers:
                            task = ready_tasks[0]
                            await self.state_machine.transition(
                                task=task,
                                new_status=TaskStatus.queued,
                                reason="Scheduled by PM",
                                actor="pm",
                                db_session=db,
                                stream_manager=self.stream_manager,
                            )

                        await db.commit()

                        # Publish phase events after successful commit
                        for event_type, event_data in phase_events:
                            await self.stream_manager.publish_board_event(event_type, event_data)
            except Exception:
                logger.exception("Scheduling loop error")

            await asyncio.sleep(5)

    async def _check_and_advance_phase(
        self, project_id: uuid.UUID, db: AsyncSession
    ) -> list[tuple[str, dict[str, str]]]:
        """Check if active phase is complete and advance to the next phase.

        Returns a list of (event_type, event_data) tuples to be published
        after the DB transaction is committed.
        """
        events: list[tuple[str, dict[str, str]]] = []

        phase_repo = PhaseRepository(db)
        active_phase = await phase_repo.get_active_phase(project_id)
        if active_phase is None:
            return events

        incomplete = await phase_repo.count_incomplete_tasks(active_phase.id)
        if incomplete > 0:
            return events

        # Phase completed
        active_phase.status = PhaseStatus.completed
        events.append((
            "phase_completed",
            {
                "phase_id": str(active_phase.id),
                "project_id": str(project_id),
                "phase_name": active_phase.name,
                "phase_order": str(active_phase.order),
            },
        ))

        # Activate next phase
        next_phase = await phase_repo.get_next_pending_phase(project_id, active_phase.order)
        if next_phase is not None:
            next_phase.status = PhaseStatus.active
            events.append((
                "phase_activated",
                {
                    "phase_id": str(next_phase.id),
                    "project_id": str(project_id),
                    "phase_name": next_phase.name,
                    "phase_order": str(next_phase.order),
                },
            ))

        return events

    async def _results_loop(self, project_id: uuid.UUID, db_session_factory: Any) -> None:
        """Consume task results and process them."""
        while self._running:
            try:
                messages = await self.stream_manager.consume(
                    stream=RedisStreamManager.TASKS_RESULTS,
                    group=RedisStreamManager.GROUP_PM,
                    consumer="pm-0",
                    count=10,
                    block=5000,
                )

                for msg in messages:
                    try:
                        async with db_session_factory() as db:
                            await self._process_result(msg, db)
                            await db.commit()
                        # ACK only after successful commit to ensure atomicity
                        await self.stream_manager.acknowledge(
                            RedisStreamManager.TASKS_RESULTS,
                            RedisStreamManager.GROUP_PM,
                            msg["_message_id"],
                        )
                    except Exception:
                        logger.exception("Result processing error for message %s", msg.get("_message_id"))
            except Exception:
                if self._running:
                    logger.exception("Results loop error")
                    await asyncio.sleep(5)

    async def _process_result(self, result: dict[str, Any], db: AsyncSession) -> None:
        """Process a single result message."""
        task_id = result.get("task_id", "")
        result_type = result.get("type", "execution")
        success = result.get("success") in ("true", True)

        repo = TaskRepository(db)
        task = await repo.get_by_id(uuid.UUID(task_id) if isinstance(task_id, str) else task_id)
        if not task:
            return

        # Store commit_hash from worker if provided
        commit_hash = result.get("commit_hash", "")
        if commit_hash:
            task.commit_hash = commit_hash

        worker_id = result.get("worker_id", "")

        if result_type == "execution":
            # Transition to in_progress first if task is still queued
            if task.status == TaskStatus.queued:
                await self.state_machine.transition(
                    task=task,
                    new_status=TaskStatus.in_progress,
                    reason="Worker started execution",
                    actor="pm",
                    db_session=db,
                    stream_manager=self.stream_manager,
                    worker_id=worker_id,
                )

            if success:
                await self._assign_reviewer(task, db, worker_id)
            else:
                error_msg = result.get("error_message", "")
                await self._handle_execution_failure(task, db, worker_id, error_msg)

        elif result_type == "qa":
            passed = result.get("passed") in ("true", True)
            if passed:
                await self.state_machine.transition(
                    task=task,
                    new_status=TaskStatus.done,
                    reason="QA passed",
                    actor="pm",
                    db_session=db,
                    stream_manager=self.stream_manager,
                )
            else:
                feedback = result.get("feedback", "")
                await self._handle_qa_failure(task, db, worker_id, feedback)

            # Set reviewer back to idle
            if worker_id:
                await self.registry.set_idle(worker_id)

    async def _handle_execution_failure(
        self, task: Task, db: AsyncSession, worker_id: str, error_msg: str
    ) -> None:
        """Handle execution failure with auto-retry or escalation to redesign."""
        task.retry_count += 1

        if task.qa_feedback_history is None:
            task.qa_feedback_history = []
        task.qa_feedback_history.append({
            "type": "execution_failure",
            "attempt": task.retry_count,
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if task.retry_count >= task.max_retries:
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.redesign,
                reason=f"Max retries ({task.max_retries}) exceeded. Last error: {error_msg}",
                actor="pm",
                db_session=db,
                stream_manager=self.stream_manager,
            )
        else:
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.ready,
                reason=f"Execution failed (attempt {task.retry_count}/{task.max_retries}): {error_msg}",
                actor="pm",
                db_session=db,
                stream_manager=self.stream_manager,
            )

        # Set worker back to idle
        if worker_id:
            await self.registry.set_idle(worker_id)

    async def _handle_qa_failure(
        self, task: Task, db: AsyncSession, worker_id: str, feedback: str
    ) -> None:
        """Handle QA failure with auto-retry or escalation to redesign."""
        task.retry_count += 1

        if task.qa_feedback_history is None:
            task.qa_feedback_history = []
        task.qa_feedback_history.append({
            "type": "qa_failure",
            "attempt": task.retry_count,
            "feedback": feedback,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if task.retry_count >= task.max_retries:
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.redesign,
                reason=f"Max retries ({task.max_retries}) exceeded. Last QA feedback: {feedback}",
                actor="pm",
                db_session=db,
                stream_manager=self.stream_manager,
            )
        else:
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.in_progress,
                reason=f"QA failed (attempt {task.retry_count}/{task.max_retries}), auto-retrying",
                actor="pm",
                db_session=db,
                stream_manager=self.stream_manager,
            )
            # Re-queue the task with QA feedback for the worker
            await self._requeue_with_feedback(task, db, feedback)

    async def _requeue_with_feedback(self, task: Task, db: AsyncSession, feedback: str) -> None:
        """Re-queue a task for execution with QA feedback included in the prompt."""
        message: dict[str, Any] = {
            "task_id": str(task.id),
            "project_id": str(task.project_id),
            "priority": task.priority.value,
            "title": task.title,
            "retry_feedback": feedback,
            "retry_count": str(task.retry_count),
        }
        if task.branch_name:
            message["branch_name"] = task.branch_name
        if task.worker_prompt:
            prompt_text = task.worker_prompt if isinstance(task.worker_prompt, str) else json.dumps(task.worker_prompt)
            message["worker_prompt"] = prompt_text
        # Include repo_path
        project_repo = ProjectRepository(db)
        project = await project_repo.get_by_id(task.project_id, load_phases=False)
        if project:
            message["repo_path"] = project.repo_path
        await self.stream_manager.publish("tasks:queue", message)

    async def _assign_reviewer(self, task: Task, db: AsyncSession, executor_worker_id: str) -> None:
        """Assign the executor worker as reviewer (code lives on that worker)."""
        await self.state_machine.transition(
            task=task,
            new_status=TaskStatus.review,
            reason="Assigned reviewer (same worker)",
            actor="pm",
            db_session=db,
            stream_manager=self.stream_manager,
            reviewer_id=executor_worker_id,
        )

    # ── Escalation Loop (Auto-Redesign) ────────────────────────────────

    async def _escalation_loop(self, project_id: uuid.UUID, db_session_factory: Any) -> None:
        """Consume escalation messages and auto-redesign tasks via Architect LLM."""
        while self._running:
            try:
                messages = await self.stream_manager.consume(
                    stream=RedisStreamManager.TASKS_ESCALATION,
                    group=RedisStreamManager.GROUP_ARCHITECT,
                    consumer="architect-0",
                    count=1,
                    block=5000,
                )
                for msg in messages:
                    try:
                        msg_project_id = msg.get("project_id", "")
                        if str(project_id) != str(msg_project_id):
                            await self.stream_manager.acknowledge(
                                RedisStreamManager.TASKS_ESCALATION,
                                RedisStreamManager.GROUP_ARCHITECT,
                                msg["_message_id"],
                            )
                            continue

                        async with db_session_factory() as db:
                            await self._process_escalation(msg, db)
                            await db.commit()
                        await self.stream_manager.acknowledge(
                            RedisStreamManager.TASKS_ESCALATION,
                            RedisStreamManager.GROUP_ARCHITECT,
                            msg["_message_id"],
                        )
                    except Exception:
                        logger.exception("Escalation processing error for message %s", msg.get("_message_id"))
                        # ACK to prevent infinite retry on permanently failing messages
                        try:
                            await self.stream_manager.acknowledge(
                                RedisStreamManager.TASKS_ESCALATION,
                                RedisStreamManager.GROUP_ARCHITECT,
                                msg["_message_id"],
                            )
                        except Exception:
                            logger.exception("Failed to ACK escalation message after error")
            except Exception:
                if self._running:
                    logger.exception("Escalation loop error")
                    await asyncio.sleep(5)

    async def _process_escalation(self, msg: dict[str, Any], db: AsyncSession) -> None:
        """Process a single escalation message: call LLM and apply redesign action."""
        task_id = msg.get("task_id", "")
        task_repo = TaskRepository(db)
        task = await task_repo.get_by_id(uuid.UUID(task_id) if isinstance(task_id, str) else task_id)
        if not task:
            logger.warning("Escalation: task %s not found, skipping", task_id)
            return
        if task.status != TaskStatus.redesign:
            logger.info("Escalation: task %s not in redesign status (%s), skipping", task_id, task.status.value)
            return

        # Detect deterministic environment errors that auto-redesign cannot fix
        if self._is_environment_error(task.error_message):
            logger.info("Escalation: task %s has environment error, skipping auto-redesign", task_id)
            await self.stream_manager.publish_board_event("auto_redesign_failed", {
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "reason": f"Environment error (not fixable by redesign): {task.error_message}",
            })
            return

        # Check auto-redesign limit via Redis counter (ephemeral, per-redesign cycle)
        redis_key = f"task:{task.id}:auto_redesign_count"
        count_raw = await self.stream_manager.redis.get(redis_key)
        auto_redesign_count = int(count_raw) if count_raw else 0

        if auto_redesign_count >= settings.max_auto_redesigns:
            logger.info(
                "Escalation: task %s reached max auto-redesigns (%d), leaving for manual intervention",
                task_id, auto_redesign_count,
            )
            await self.stream_manager.publish_board_event("auto_redesign_failed", {
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "reason": f"Max auto-redesign attempts ({settings.max_auto_redesigns}) reached",
            })
            return

        # Load project for LLM config
        project_repo = ProjectRepository(db)
        project = await project_repo.get_by_id(task.project_id, load_phases=False)
        if not project:
            logger.warning("Escalation: project %s not found for task %s", task.project_id, task_id)
            await self.stream_manager.publish_board_event("auto_redesign_failed", {
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "reason": "Project not found",
            })
            return

        # Create LLM client
        try:
            llm_client = create_llm_client_from_project(project, role="architect")
        except ValueError as e:
            logger.warning("Escalation: no LLM config for project %s: %s", project.id, e)
            await self.stream_manager.publish_board_event("auto_redesign_failed", {
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "reason": f"No architect LLM configuration: {e}",
            })
            return

        # Build prompt context
        worker_prompt_text = ""
        if task.worker_prompt:
            worker_prompt_text = (
                task.worker_prompt.get("prompt", json.dumps(task.worker_prompt))
                if isinstance(task.worker_prompt, dict)
                else str(task.worker_prompt)
            )
        qa_prompt_text = ""
        if task.qa_prompt:
            qa_prompt_text = (
                task.qa_prompt.get("prompt", json.dumps(task.qa_prompt))
                if isinstance(task.qa_prompt, dict)
                else str(task.qa_prompt)
            )

        failure_history = json.dumps(task.qa_feedback_history or [], indent=2)

        prompt = get_prompt("architect", "redesign").format(
            title=task.title,
            description=task.description or "No description",
            priority=task.priority.value,
            retry_count=task.retry_count,
            max_retries=task.max_retries,
            branch_name=task.branch_name or "N/A",
            worker_prompt=worker_prompt_text or "No worker prompt",
            qa_prompt=qa_prompt_text or "No QA prompt",
            failure_history=failure_history,
            error_message=task.error_message or "No error message",
        )

        llm_messages = [
            {"role": "system", "content": get_prompt("architect", "system")},
            {"role": "user", "content": prompt},
        ]

        # Call LLM
        try:
            result = await llm_client.structured_output(
                messages=llm_messages,
                response_format={"type": "json_object"},
            )
        except LLMError as e:
            logger.error("Escalation: LLM call failed for task %s: %s", task_id, e)
            await self.stream_manager.publish_board_event("auto_redesign_failed", {
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "reason": f"LLM error: {e}",
            })
            return

        # Apply the action
        action = result.get("action", "").lower()
        reasoning = result.get("reasoning", "")

        await self._apply_redesign_action(task, action, result, reasoning, db)

        # Increment Redis counter with TTL (auto-expires after redesign cycle)
        await self.stream_manager.redis.incr(redis_key)
        await self.stream_manager.redis.expire(redis_key, 86400)  # 24h TTL

        # Publish success event
        await self.stream_manager.publish_board_event("auto_redesign_applied", {
            "task_id": str(task.id),
            "project_id": str(task.project_id),
            "action": action,
            "reasoning": reasoning,
        })

        logger.info("Auto-redesign applied for task %s: action=%s, reasoning=%s", task_id, action, reasoning)

    async def _apply_redesign_action(
        self,
        task: Task,
        action: str,
        result: dict[str, Any],
        reasoning: str,
        db: AsyncSession,
    ) -> None:
        """Apply a redesign action decided by the Architect LLM."""
        if action == "modify":
            if result.get("title"):
                task.title = result["title"]
            if result.get("description"):
                task.description = result["description"]
            if result.get("worker_prompt"):
                task.worker_prompt = {"prompt": result["worker_prompt"]}
            if result.get("qa_prompt"):
                task.qa_prompt = {"prompt": result["qa_prompt"]}
            # Reset retry state
            task.retry_count = 0
            task.qa_feedback_history = None
            task.error_message = None
            task.commit_hash = None
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.waiting,
                reason=f"Auto-redesigned by Architect (modify): {reasoning}",
                actor="architect",
                db_session=db,
                stream_manager=self.stream_manager,
            )

        elif action == "delete":
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.done,
                reason=f"Removed by Auto-Architect (delete): {reasoning}",
                actor="architect",
                db_session=db,
                stream_manager=self.stream_manager,
            )

        elif action == "split":
            split_tasks = result.get("split_tasks", [])
            if not split_tasks:
                logger.warning("Escalation: LLM returned split but no split_tasks for task %s", task.id)
                return

            # Mark original as done
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.done,
                reason=f"Split into {len(split_tasks)} sub-tasks by Auto-Architect: {reasoning}",
                actor="architect",
                db_session=db,
                stream_manager=self.stream_manager,
            )

            # Create new sub-tasks
            for sub in split_tasks:
                priority_str = sub.get("priority", "medium")
                try:
                    priority = TaskPriority(priority_str)
                except ValueError:
                    priority = TaskPriority.medium

                new_task = Task(
                    project_id=task.project_id,
                    phase_id=task.phase_id,
                    title=sub.get("title", "Untitled Sub-Task"),
                    description=sub.get("description"),
                    priority=priority,
                    status=TaskStatus.waiting,
                    worker_prompt={"prompt": sub.get("worker_prompt", "")},
                    qa_prompt={"prompt": sub.get("qa_prompt", "")},
                    branch_name=task.branch_name,
                )
                db.add(new_task)
        else:
            logger.warning("Escalation: unknown action '%s' from LLM for task %s", action, task.id)

    @staticmethod
    def _is_environment_error(error_message: str | None) -> bool:
        """Check if the error is a deterministic environment issue that redesign cannot fix."""
        if not error_message:
            return False
        patterns = [
            "WinError 2",           # File not found (e.g. CLI binary missing)
            "WinError 3",           # Path not found
            "FileNotFoundError",
            "No such file or directory",
            "PermissionError",
            "EACCES",
            "ENOENT",
            "command not found",
        ]
        lower = error_message.lower()
        return any(p.lower() in lower for p in patterns)

    async def queue_next(self, project_id: uuid.UUID, db: AsyncSession) -> Task | None:
        """Manually queue the next ready task (respects sequential constraint)."""
        repo = TaskRepository(db)

        # Sequential constraint: only one task at a time per project
        active_count = await repo.count_active_tasks(project_id)
        if active_count > 0:
            return None

        ready_tasks = await repo.list_ready_by_priority(project_id)
        if ready_tasks:
            task = ready_tasks[0]
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.queued,
                reason="Manually queued",
                actor="user",
                db_session=db,
                stream_manager=self.stream_manager,
            )
            return task
        return None
