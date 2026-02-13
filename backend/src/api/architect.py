from __future__ import annotations

import json
import re
import unicodedata
import uuid
from typing import Any

from backend.src import models, schemas
from backend.src.core.llm_client import LLMClient, LLMConfig, LLMError
from backend.src.prompts.loader import get_prompt
from backend.src.repositories.design_session_repository import DesignSessionRepository
from backend.src.repositories.phase_repository import PhaseRepository
from backend.src.repositories.project_repository import ProjectRepository
from backend.src.repositories.task_repository import TaskRepository
from backend.src.storage.database import get_db
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/v1/architect", tags=["architect"])


def _slugify(value: str) -> str:
    """Convert a string to a URL-friendly slug."""
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


def _build_llm_config(llm_config_dict: dict[str, Any] | None) -> LLMConfig:
    """Build an LLMConfig from a dict stored in session.llm_config."""
    if not llm_config_dict or "api_key" not in llm_config_dict:
        raise ValueError("LLM configuration with api_key is required")
    return LLMConfig(
        api_key=llm_config_dict["api_key"],
        model=llm_config_dict.get("model") or "anthropic/claude-sonnet-4-20250514",
        base_url=llm_config_dict.get("base_url"),
    )


def _build_message_history(session: models.DesignSession) -> list[dict[str, str]]:
    """Build LLM message history from a session's messages.

    Prepends the system prompt from the prompt template with role='system',
    then appends all stored messages (user + assistant) in chronological order.
    """
    history: list[dict[str, str]] = [
        {"role": "system", "content": get_prompt("architect", "system")},
    ]
    chat_messages = [m for m in session.messages if m.message_type == models.MessageType.chat]
    sorted_messages = sorted(chat_messages, key=lambda m: m.created_at)
    history.extend(
        {
            "role": (
                m.role.value if isinstance(m.role, models.MessageRole) else str(m.role)
            ),
            "content": m.content,
        }
        for m in sorted_messages
    )
    return history


# ── 0. List Sessions ─────────────────────────────────────────────────


@router.get("/sessions", response_model=list[schemas.DesignSessionResponse])
async def list_sessions(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[schemas.DesignSessionResponse]:
    """List all design sessions, optionally filtered by status."""
    repo = DesignSessionRepository(db)
    status_filter = None
    if status is not None:
        try:
            status_filter = models.DesignSessionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    sessions = await repo.list_sessions(status=status_filter)
    for s in sessions:
        s.messages = [m for m in s.messages if m.message_type == models.MessageType.chat]
    return [schemas.DesignSessionResponse.model_validate(s) for s in sessions]


# ── 1. Create Session ────────────────────────────────────────────────


@router.post("/sessions", response_model=schemas.DesignSessionResponse, status_code=201)
async def create_session(
    body: schemas.CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> schemas.DesignSessionResponse:
    """Create a new design session with an initial system message."""
    llm_config_dict: dict[str, Any] = {
        "api_key": body.llm_config.api_key,
    }
    if body.llm_config.model:
        llm_config_dict["model"] = body.llm_config.model
    if body.llm_config.base_url:
        llm_config_dict["base_url"] = body.llm_config.base_url

    repo = DesignSessionRepository(db)
    session = await repo.add(models.DesignSession(name=body.name, llm_config=llm_config_dict))
    await repo.commit()

    # Reload with messages
    loaded = await repo.get_by_id(session.id)
    if loaded is None:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return schemas.DesignSessionResponse.model_validate(loaded)


# ── 2. Get Session ───────────────────────────────────────────────────


@router.get("/sessions/{session_id}", response_model=schemas.DesignSessionResponse)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> schemas.DesignSessionResponse:
    """Get a design session with all messages."""
    repo = DesignSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.messages = [m for m in session.messages if m.message_type == models.MessageType.chat]
    return schemas.DesignSessionResponse.model_validate(session)


# ── 3. REST Message (non-streaming) ─────────────────────────────────


@router.post(
    "/sessions/{session_id}/message", response_model=schemas.DesignMessageResponse
)
async def send_message(
    session_id: uuid.UUID,
    body: schemas.MessageRequest,
    db: AsyncSession = Depends(get_db),
) -> schemas.DesignMessageResponse:
    """Send a message and get a non-streaming LLM response."""
    repo = DesignSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != models.DesignSessionStatus.active:
        raise HTTPException(status_code=400, detail="Session is not active")

    # Save user message
    await repo.add_message(session.id, models.MessageRole.user, body.content)

    # Build message history and call LLM
    messages = _build_message_history(session)
    messages.append({"role": "user", "content": body.content})

    config = _build_llm_config(session.llm_config)
    client = LLMClient(config)

    try:
        response_text = await client.chat(messages)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e

    # Save assistant response
    assistant_msg = await repo.add_message(
        session.id, models.MessageRole.assistant, response_text
    )
    await repo.commit()
    await repo.refresh(assistant_msg)

    return schemas.DesignMessageResponse.model_validate(assistant_msg)


# ── 4. SSE Streaming Message ────────────────────────────────────────


@router.post("/sessions/{session_id}/message/stream")
async def send_message_stream(
    session_id: uuid.UUID,
    body: schemas.MessageRequest,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Send a message and stream the LLM response via SSE."""
    repo = DesignSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != models.DesignSessionStatus.active:
        raise HTTPException(status_code=400, detail="Session is not active")

    # Save user message
    await repo.add_message(session.id, models.MessageRole.user, body.content)

    # Build message history
    messages = _build_message_history(session)
    messages.append({"role": "user", "content": body.content})

    config = _build_llm_config(session.llm_config)
    client = LLMClient(config)

    async def event_generator():
        full_response = ""
        try:
            async for chunk in client.stream_chat(messages):
                full_response += chunk
                yield {"event": "chunk", "data": chunk}
        except LLMError as e:
            yield {"event": "error", "data": str(e)}
            return

        # Save assistant response
        await repo.add_message(session.id, models.MessageRole.assistant, full_response)
        await repo.commit()

        yield {"event": "done", "data": full_response}

    return EventSourceResponse(event_generator())


# ── 5. WebSocket Chat ────────────────────────────────────────────────


async def architect_websocket(
    websocket: WebSocket, session_id: uuid.UUID
) -> None:
    """WebSocket handler for architect chat. Registered on the app in main.py.

    Uses short-lived DB sessions per operation to avoid holding a connection
    from the pool for the entire (long-lived) WebSocket lifetime.
    """
    from backend.src.storage.database import async_session

    await websocket.accept()

    # Load session with a short-lived DB session
    async with async_session() as db:
        repo = DesignSessionRepository(db)
        session = await repo.get_by_id(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "content": "Session not found"})
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") != "message":
                await websocket.send_json(
                    {"type": "error", "content": "Unknown message type"}
                )
                continue

            content = data.get("content", "")
            if not content:
                await websocket.send_json({"type": "error", "content": "Empty message"})
                continue

            # Save user message and reload session in a short-lived DB session
            async with async_session() as db:
                repo = DesignSessionRepository(db)
                await repo.add_message(session.id, models.MessageRole.user, content)
                await repo.commit()

                # Reload session with messages to get the latest
                reloaded = await repo.get_by_id(session_id)
            if reloaded is None:
                await websocket.send_json(
                    {"type": "error", "content": "Session not found"}
                )
                break
            session = reloaded

            # Build message history
            messages = _build_message_history(session)

            config = _build_llm_config(session.llm_config)
            client = LLMClient(config)

            full_response = ""
            try:
                async for chunk in client.stream_chat(messages):
                    full_response += chunk
                    await websocket.send_json({"type": "chunk", "content": chunk})
            except LLMError as e:
                await websocket.send_json({"type": "error", "content": str(e)})
                continue

            # Save assistant response in a short-lived DB session
            async with async_session() as db:
                repo = DesignSessionRepository(db)
                await repo.add_message(
                    session.id, models.MessageRole.assistant, full_response
                )
                await repo.commit()

            await websocket.send_json({"type": "done", "content": full_response})

    except WebSocketDisconnect:
        pass


# ── 6. Finalize Design ──────────────────────────────────────────────


@router.post("/sessions/{session_id}/finalize", response_model=schemas.ProjectResponse)
async def finalize_design(
    session_id: uuid.UUID,
    body: schemas.FinalizeRequest,
    db: AsyncSession = Depends(get_db),
) -> schemas.ProjectResponse:
    """Finalize a design session into a project with phases and tasks."""
    session_repo = DesignSessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != models.DesignSessionStatus.active:
        raise HTTPException(status_code=400, detail="Session is not active")

    # Build message history and add finalize prompt
    messages = _build_message_history(session)
    messages.append({"role": "user", "content": get_prompt("architect", "finalize")})

    config = _build_llm_config(session.llm_config)
    client = LLMClient(config)

    try:
        result = await client.structured_output(
            messages=messages,
            response_format={"type": "json_object"},
        )
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e

    # Store finalize prompt and response as internal messages for auditability
    await session_repo.add_message(
        session.id,
        models.MessageRole.user,
        get_prompt("architect", "finalize"),
        message_type=models.MessageType.internal,
    )
    await session_repo.add_message(
        session.id,
        models.MessageRole.assistant,
        json.dumps(result, ensure_ascii=False),
        message_type=models.MessageType.internal,
    )

    # Build llm_config for the project
    project_llm_config: dict[str, Any] = {
        "architect": session.llm_config,
    }
    if body.pm_llm_config:
        project_llm_config["pm"] = {
            "api_key": body.pm_llm_config.api_key,
        }
        if body.pm_llm_config.model:
            project_llm_config["pm"]["model"] = body.pm_llm_config.model
        if body.pm_llm_config.base_url:
            project_llm_config["pm"]["base_url"] = body.pm_llm_config.base_url

    # Create project
    project = models.Project(
        name=result.get("project_name", "Untitled Project"),
        description=result.get("project_description", ""),
        repo_path=body.repo_path,
        status=models.ProjectStatus.design,
        llm_config=project_llm_config,
    )
    db.add(project)
    await db.flush()

    # Create phases and tasks, collecting all tasks in a flat list for dependency resolution
    all_tasks: list[models.Task] = []
    phases_data = result.get("phases", [])

    for phase_order, phase_data in enumerate(phases_data, start=1):
        phase_name = phase_data.get("name", f"Phase {phase_order}")
        branch_name = f"phase/{_slugify(phase_name)}"

        phase = models.Phase(
            project_id=project.id,
            name=phase_name,
            description=phase_data.get("description"),
            branch_name=branch_name,
            order=phase_order,
        )
        db.add(phase)
        await db.flush()

        for task_data in phase_data.get("tasks", []):
            priority_str = task_data.get("priority", "medium")
            try:
                priority = models.TaskPriority(priority_str)
            except ValueError:
                priority = models.TaskPriority.medium

            task = models.Task(
                project_id=project.id,
                phase_id=phase.id,
                title=task_data.get("title", "Untitled Task"),
                description=task_data.get("description"),
                priority=priority,
                worker_prompt={"prompt": task_data.get("worker_prompt", "")},
                qa_prompt={"prompt": task_data.get("qa_prompt", "")},
            )
            db.add(task)
            await db.flush()
            all_tasks.append(task)

    # Wire up dependencies using depends_on_indices
    task_repo = TaskRepository(db)
    tasks_with_deps: set[int] = set()
    flat_index = 0
    for phase_data in phases_data:
        for task_data in phase_data.get("tasks", []):
            depends_on_indices = task_data.get("depends_on_indices", [])
            if depends_on_indices:
                dep_ids = []
                for idx in depends_on_indices:
                    if 0 <= idx < len(all_tasks):
                        dep_ids.append(all_tasks[idx].id)
                if dep_ids:
                    await task_repo.add_dependencies(all_tasks[flat_index].id, dep_ids)
                    all_tasks[flat_index].status = models.TaskStatus.waiting
                    tasks_with_deps.add(flat_index)
            flat_index += 1

    # Promote dependency-free tasks to ready
    for i, task in enumerate(all_tasks):
        if i not in tasks_with_deps:
            task.status = models.TaskStatus.ready

    # Update session status and link to project
    session.status = models.DesignSessionStatus.finalized
    session.project_id = project.id
    await session_repo.commit()

    # Reload project with phases
    project_repo = ProjectRepository(db)
    loaded_project = await project_repo.get_by_id(project.id)
    return schemas.ProjectResponse.model_validate(loaded_project)


# ── 7. Add Task to Existing Project ─────────────────────────────────


@router.post(
    "/add-task/{project_id}", response_model=schemas.AddTaskResponse, status_code=201
)
async def add_task(
    project_id: uuid.UUID,
    body: schemas.AddTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> schemas.AddTaskResponse:
    """Add a task to an existing project using LLM."""
    project_repo = ProjectRepository(db)
    project = await project_repo.get_by_id(project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify phase belongs to project
    phase_repo = PhaseRepository(db)
    phase = await phase_repo.get_by_id(body.phase_id)

    if phase is None:
        raise HTTPException(status_code=404, detail="Phase not found")

    if phase.project_id != project.id:
        raise HTTPException(
            status_code=400, detail="Phase does not belong to this project"
        )

    # Get project context (existing phases + tasks)
    phases = await phase_repo.list_by_project(project_id)
    task_repo = TaskRepository(db)
    existing_tasks = await task_repo.list_by_project(project_id)

    context = f"Project: {project.name}\nDescription: {project.description}\n\nExisting phases:\n"
    for p in phases:
        context += f"- {p.name}: {p.description or 'No description'}\n"
    context += "\nExisting tasks:\n"
    for t in existing_tasks:
        context += (
            f"- [{t.priority.value}] {t.title}: {t.description or 'No description'}\n"
        )

    prompt = get_prompt("architect", "add_task").format(
        context=context,
        phase_name=phase.name,
        request_text=body.request_text,
    )

    # Determine LLM config: override from request body, project config, or fail
    llm_config_dict: dict[str, Any] | None = None
    if body.llm_config:
        llm_config_dict = {"api_key": body.llm_config.api_key}
        if body.llm_config.model:
            llm_config_dict["model"] = body.llm_config.model
        if body.llm_config.base_url:
            llm_config_dict["base_url"] = body.llm_config.base_url
    elif project.llm_config and project.llm_config.get("architect"):
        llm_config_dict = project.llm_config["architect"]

    if not llm_config_dict or not llm_config_dict.get("api_key"):
        raise HTTPException(
            status_code=400,
            detail="No LLM configuration available. Provide llm_config in request or configure project.",
        )

    config = _build_llm_config(llm_config_dict)
    client = LLMClient(config)

    messages = [
        {"role": "system", "content": get_prompt("architect", "system")},
        {"role": "user", "content": prompt},
    ]

    try:
        result = await client.structured_output(
            messages=messages,
            response_format={"type": "json_object"},
        )
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e

    priority_str = result.get("priority", "medium")
    try:
        priority = models.TaskPriority(priority_str)
    except ValueError:
        priority = models.TaskPriority.medium

    task = models.Task(
        project_id=project.id,
        phase_id=phase.id,
        title=result.get("title", "Untitled Task"),
        description=result.get("description"),
        priority=priority,
        status=models.TaskStatus.ready,
        worker_prompt={"prompt": result.get("worker_prompt", "")},
        qa_prompt={"prompt": result.get("qa_prompt", "")},
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return schemas.AddTaskResponse.model_validate(task)
