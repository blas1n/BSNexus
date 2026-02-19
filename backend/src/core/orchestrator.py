from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.state_machine import TaskStateMachine
from backend.src.models import PhaseStatus, Task, TaskStatus
from backend.src.queue.streams import RedisStreamManager
from backend.src.repositories.phase_repository import PhaseRepository
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
                        await asyncio.sleep(5)
                        continue

                    # Check phase completion and advance to next phase if needed
                    await self._check_and_advance_phase(project_id, db)

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
            except Exception:
                logger.exception("Scheduling loop error")

            await asyncio.sleep(5)

    async def _check_and_advance_phase(self, project_id: uuid.UUID, db: AsyncSession) -> None:
        """Check if active phase is complete and advance to the next phase."""
        phase_repo = PhaseRepository(db)
        active_phase = await phase_repo.get_active_phase(project_id)
        if active_phase is None:
            return

        incomplete = await phase_repo.count_incomplete_tasks(active_phase.id)
        if incomplete > 0:
            return

        # Phase completed
        active_phase.status = PhaseStatus.completed
        await self.stream_manager.publish_board_event(
            "phase_completed",
            {
                "phase_id": str(active_phase.id),
                "project_id": str(project_id),
                "phase_name": active_phase.name,
                "phase_order": str(active_phase.order),
            },
        )

        # Activate next phase
        next_phase = await phase_repo.get_next_pending_phase(project_id, active_phase.order)
        if next_phase is not None:
            next_phase.status = PhaseStatus.active
            await self.stream_manager.publish_board_event(
                "phase_activated",
                {
                    "phase_id": str(next_phase.id),
                    "project_id": str(project_id),
                    "phase_name": next_phase.name,
                    "phase_order": str(next_phase.order),
                },
            )

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
        from backend.src.repositories.project_repository import ProjectRepository

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
