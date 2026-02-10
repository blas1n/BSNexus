from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from backend.src.core.git_ops import GitOps
    from backend.src.core.prompt_security import PromptSigner

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.models import Task, TaskHistory, TaskStatus
from backend.src.queue.streams import RedisStreamManager
from backend.src.repositories.task_repository import TaskRepository


class TaskStateMachine:
    """State machine for managing task status transitions."""

    TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
        TaskStatus.waiting: {TaskStatus.ready},
        TaskStatus.ready: {TaskStatus.queued},
        TaskStatus.queued: {TaskStatus.in_progress},
        TaskStatus.in_progress: {TaskStatus.review, TaskStatus.rejected},
        TaskStatus.review: {TaskStatus.done, TaskStatus.rejected},
        TaskStatus.done: {TaskStatus.rejected},
        TaskStatus.rejected: {TaskStatus.ready},
    }

    def __init__(
        self,
        git_ops: GitOps | None = None,
        prompt_signer: PromptSigner | None = None,
    ) -> None:
        self.git_ops = git_ops
        self.prompt_signer = prompt_signer

    def can_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """Check if a transition is allowed."""
        allowed = self.TRANSITIONS.get(from_status, set())
        return to_status in allowed

    async def transition(
        self,
        task: Task,
        new_status: TaskStatus,
        reason: Optional[str] = None,
        actor: str = "system",
        db_session: Optional[AsyncSession] = None,
        stream_manager: Optional[RedisStreamManager] = None,
        **kwargs: Any,
    ) -> Task:
        """Execute a state transition with side effects."""
        old_status = task.status

        # 1. Validate transition
        if not self.can_transition(old_status, new_status):
            raise ValueError(f"Invalid transition: {old_status.value} -> {new_status.value}")

        # 2. Record history (requires db_session)
        if db_session is not None:
            history = TaskHistory(
                task_id=task.id,
                from_status=old_status.value,
                to_status=new_status.value,
                actor=actor,
                reason=reason,
                extra_metadata=kwargs if kwargs else None,
            )
            db_session.add(history)

        # 3. Update task status + version (optimistic locking)
        task.status = new_status
        task.version += 1

        # 4. Execute side effects
        await self._execute_side_effects(task, old_status, new_status, db_session, stream_manager, **kwargs)

        # 5. Publish board event
        if stream_manager is not None:
            await stream_manager.publish_board_event(
                "task_transition",
                {
                    "task_id": str(task.id),
                    "project_id": str(task.project_id),
                    "from_status": old_status.value,
                    "to_status": new_status.value,
                    "actor": actor,
                },
            )

        return task

    async def _execute_side_effects(
        self,
        task: Task,
        old_status: TaskStatus,
        new_status: TaskStatus,
        db_session: Optional[AsyncSession],
        stream_manager: Optional[RedisStreamManager],
        **kwargs: Any,
    ) -> None:
        """Dispatch side effects based on the new status."""
        side_effect_map = {
            TaskStatus.ready: self._on_ready,
            TaskStatus.queued: self._on_queued,
            TaskStatus.in_progress: self._on_in_progress,
            TaskStatus.review: self._on_review,
            TaskStatus.done: self._on_done,
            TaskStatus.rejected: self._on_rejected,
        }
        handler = side_effect_map.get(new_status)
        if handler is not None:
            await handler(task, db_session=db_session, stream_manager=stream_manager, **kwargs)

    async def _on_ready(
        self,
        task: Task,
        *,
        db_session: Optional[AsyncSession] = None,
        stream_manager: Optional[RedisStreamManager] = None,
        **kwargs: Any,
    ) -> None:
        """No-op: dependency check is done by the caller."""

    async def _on_queued(
        self,
        task: Task,
        *,
        db_session: Optional[AsyncSession] = None,
        stream_manager: Optional[RedisStreamManager] = None,
        **kwargs: Any,
    ) -> None:
        """Publish task to the work queue via Redis Streams."""
        if stream_manager is not None:
            message: dict[str, Any] = {
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "priority": task.priority.value,
                "title": task.title,
            }
            if self.prompt_signer and task.worker_prompt:
                prompt_text = (
                    task.worker_prompt if isinstance(task.worker_prompt, str) else json.dumps(task.worker_prompt)
                )
                message["signed_worker_prompt"] = self.prompt_signer.sign(prompt_text)
            await stream_manager.publish("tasks:queue", message)

    async def _on_in_progress(
        self,
        task: Task,
        *,
        db_session: Optional[AsyncSession] = None,
        stream_manager: Optional[RedisStreamManager] = None,
        **kwargs: Any,
    ) -> None:
        """Set worker_id and started_at timestamp."""
        worker_id = kwargs.get("worker_id")
        if worker_id is not None:
            task.worker_id = worker_id if isinstance(worker_id, uuid.UUID) else uuid.UUID(worker_id)
        task.started_at = datetime.now(timezone.utc)

    async def _on_review(
        self,
        task: Task,
        *,
        db_session: Optional[AsyncSession] = None,
        stream_manager: Optional[RedisStreamManager] = None,
        **kwargs: Any,
    ) -> None:
        """Set reviewer_id and publish to QA queue."""
        reviewer_id = kwargs.get("reviewer_id")
        if reviewer_id is not None:
            task.reviewer_id = reviewer_id if isinstance(reviewer_id, uuid.UUID) else uuid.UUID(reviewer_id)
        if stream_manager is not None:
            message: dict[str, Any] = {
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "title": task.title,
            }
            if self.prompt_signer and task.qa_prompt:
                prompt_text = task.qa_prompt if isinstance(task.qa_prompt, str) else json.dumps(task.qa_prompt)
                message["signed_qa_prompt"] = self.prompt_signer.sign(prompt_text)
            await stream_manager.publish("tasks:qa", message)

    async def _on_done(
        self,
        task: Task,
        *,
        db_session: Optional[AsyncSession] = None,
        stream_manager: Optional[RedisStreamManager] = None,
        **kwargs: Any,
    ) -> None:
        """Set completed_at, commit via GitOps, and promote dependent tasks."""
        task.completed_at = datetime.now(timezone.utc)
        if self.git_ops and task.branch_name:
            try:
                commit_hash = await self.git_ops.commit_task(
                    str(task.id), task.title, task.branch_name
                )
                task.commit_hash = commit_hash
            except RuntimeError:
                pass  # Git failure should not block task completion
        if db_session is not None:
            repo = TaskRepository(db_session)
            await self._promote_dependents(task, repo, db_session)

    async def _on_rejected(
        self,
        task: Task,
        *,
        db_session: Optional[AsyncSession] = None,
        stream_manager: Optional[RedisStreamManager] = None,
        **kwargs: Any,
    ) -> None:
        """Set error_message from the rejection reason, and revert GitOps commit if present."""
        reason = kwargs.get("reason")
        if reason is not None:
            task.error_message = reason
        if self.git_ops and task.commit_hash:
            try:
                await self.git_ops.revert_task(task.commit_hash)
                task.commit_hash = None
            except RuntimeError:
                pass  # Git failure should not block rejection

    # -- Dependency Methods ----------------------------------------------------

    async def check_dependencies_met(self, task: Task, db_session: AsyncSession) -> bool:
        """Check if all dependency tasks are in DONE status."""
        repo = TaskRepository(db_session)
        return await repo.check_dependencies_met(task.id)

    async def _promote_dependents(self, task: Task, repo: TaskRepository, db_session: AsyncSession) -> list[Task]:
        """Promote WAITING tasks that depend on the completed task to READY."""
        waiting_tasks = await repo.find_waiting_dependents(task.id)

        promoted: list[Task] = []
        for waiting_task in waiting_tasks:
            if await repo.check_dependencies_met(waiting_task.id):
                waiting_task.status = TaskStatus.ready
                waiting_task.version += 1

                history = TaskHistory(
                    task_id=waiting_task.id,
                    from_status=TaskStatus.waiting.value,
                    to_status=TaskStatus.ready.value,
                    actor="system",
                    reason=f"All dependencies met (triggered by task {task.id})",
                )
                db_session.add(history)
                promoted.append(waiting_task)

        return promoted

    async def promote_dependents(self, task: Task, db_session: AsyncSession) -> list[Task]:
        """Promote WAITING tasks that depend on the completed task to READY (public API)."""
        repo = TaskRepository(db_session)
        return await self._promote_dependents(task, repo, db_session)
