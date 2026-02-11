from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.state_machine import TaskStateMachine
from backend.src.models import Task, TaskStatus
from backend.src.queue.streams import RedisStreamManager
from backend.src.repositories.task_repository import TaskRepository
from backend.src.utils.worker_registry import WorkerRegistry


class PMOrchestrator:
    """PM Orchestrator - task scheduling and result processing."""

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
        """Promote WAITING tasks whose dependencies are all met to READY."""
        try:
            async with db_session_factory() as db:
                repo = TaskRepository(db)
                waiting_tasks = await repo.list_by_project(project_id, status=TaskStatus.waiting, limit=500)
                for task in waiting_tasks:
                    if await repo.check_dependencies_met(task.id):
                        await self.state_machine.transition(
                            task=task,
                            new_status=TaskStatus.ready,
                            reason="All dependencies met",
                            actor="system",
                            db_session=db,
                            stream_manager=self.stream_manager,
                        )
                await db.commit()
        except Exception as e:
            print(f"Promote waiting tasks error: {e}")

    async def stop(self) -> None:
        """Stop orchestration."""
        self._running = False

    async def _scheduling_loop(self, project_id: uuid.UUID, db_session_factory: Any) -> None:
        """Schedule READY tasks to the queue based on idle workers."""
        while self._running:
            try:
                async with db_session_factory() as db:
                    repo = TaskRepository(db)
                    ready_tasks = await repo.list_ready_by_priority(project_id)
                    workers = await self.registry.get_all_workers()
                    idle_workers = [w for w in workers if w["status"] == "idle"]

                    for task in ready_tasks[: len(idle_workers)]:
                        await self.state_machine.transition(
                            task=task,
                            new_status=TaskStatus.queued,
                            reason="Scheduled by PM",
                            actor="pm",
                            db_session=db,
                            stream_manager=self.stream_manager,
                        )

                    await db.commit()
            except Exception as e:
                print(f"Scheduling loop error: {e}")

            await asyncio.sleep(5)

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
                    except Exception as e:
                        print(f"Result processing error: {e}")

                    await self.stream_manager.acknowledge(
                        RedisStreamManager.TASKS_RESULTS,
                        RedisStreamManager.GROUP_PM,
                        msg["_message_id"],
                    )
            except Exception as e:
                if self._running:
                    print(f"Results loop error: {e}")
                    await asyncio.sleep(5)

    async def _process_result(self, result: dict[str, Any], db: AsyncSession) -> None:
        """Process a single result message."""
        task_id = result.get("task_id", "")
        result_type = result.get("type", "execution")
        success = result.get("success") == "true"

        repo = TaskRepository(db)
        task = await repo.get_by_id(uuid.UUID(task_id) if isinstance(task_id, str) else task_id)
        if not task:
            return

        worker_id = result.get("worker_id", "")

        if result_type == "execution":
            if success:
                await self._assign_reviewer(task, db, worker_id)
            else:
                error_msg = result.get("error_message", "")
                await self.state_machine.transition(
                    task=task,
                    new_status=TaskStatus.rejected,
                    reason=f"Execution failed: {error_msg}",
                    actor="pm",
                    db_session=db,
                    stream_manager=self.stream_manager,
                )
                # Set worker back to idle
                if worker_id:
                    await self.registry.set_idle(worker_id)

        elif result_type == "qa":
            passed = result.get("passed") == "true"
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
                await self.state_machine.transition(
                    task=task,
                    new_status=TaskStatus.rejected,
                    reason=f"QA failed: {feedback}",
                    actor="pm",
                    db_session=db,
                    stream_manager=self.stream_manager,
                )
            # Set reviewer back to idle
            if worker_id:
                await self.registry.set_idle(worker_id)

    async def _assign_reviewer(self, task: Task, db: AsyncSession, executor_worker_id: str) -> None:
        """Assign a reviewer (different from the executor)."""
        workers = await self.registry.get_all_workers()
        available_reviewers = [w for w in workers if w["id"] != executor_worker_id and w["status"] == "idle"]

        if available_reviewers:
            reviewer = available_reviewers[0]
            await self.state_machine.transition(
                task=task,
                new_status=TaskStatus.review,
                reason="Assigned reviewer",
                actor="pm",
                db_session=db,
                stream_manager=self.stream_manager,
                reviewer_id=reviewer["id"],
            )
            await self.registry.set_busy(reviewer["id"], str(task.id))
        # If no reviewers available, leave task in IN_PROGRESS
        # Next scheduling loop will retry

    async def queue_next(self, project_id: uuid.UUID, db: AsyncSession) -> Task | None:
        """Manually queue the next ready task."""
        repo = TaskRepository(db)
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
