import enum
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Health Schemas ────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str


class DepsHealthResponse(BaseModel):
    redis: str
    postgresql: str


# ── Enums ─────────────────────────────────────────────────────────────


class TaskStatus(str, enum.Enum):
    waiting = "waiting"
    ready = "ready"
    queued = "queued"
    in_progress = "in_progress"
    review = "review"
    done = "done"
    rejected = "rejected"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ProjectStatus(str, enum.Enum):
    design = "design"
    active = "active"
    paused = "paused"
    completed = "completed"


class PhaseStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    completed = "completed"


class WorkerStatus(str, enum.Enum):
    idle = "idle"
    busy = "busy"
    offline = "offline"


# ── Phase Schemas ─────────────────────────────────────────────────────


class PhaseCreate(BaseModel):
    name: str
    description: str
    order: int


class PhaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: Optional[str] = None
    branch_name: str
    order: int
    status: PhaseStatus
    created_at: datetime
    updated_at: datetime


# ── Project Schemas ───────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str
    description: str
    repo_path: str


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    design_doc_path: Optional[str] = None
    repo_path: str
    status: ProjectStatus
    llm_config: Optional[dict] = None
    created_at: datetime
    updated_at: datetime
    phases: list[PhaseResponse] = Field(default_factory=list)


# ── Task Schemas ──────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    project_id: uuid.UUID
    phase_id: uuid.UUID
    title: str
    description: str
    priority: TaskPriority
    depends_on: list[uuid.UUID] = Field(default_factory=list)
    worker_prompt: str
    qa_prompt: str


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None


class TaskTransition(BaseModel):
    new_status: TaskStatus
    reason: Optional[str] = None
    actor: str = "user"


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    phase_id: uuid.UUID
    title: str
    description: Optional[str] = None
    status: TaskStatus
    priority: TaskPriority
    worker_prompt: Optional[dict] = None
    qa_prompt: Optional[dict] = None
    branch_name: Optional[str] = None
    commit_hash: Optional[str] = None
    worker_id: Optional[uuid.UUID] = None
    reviewer_id: Optional[uuid.UUID] = None
    qa_result: Optional[dict] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    version: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    depends_on: list[uuid.UUID] = Field(default_factory=list)


# ── Worker Schemas ────────────────────────────────────────────────────


class WorkerRegister(BaseModel):
    name: Optional[str] = None
    platform: str
    capabilities: Optional[dict] = None
    executor_type: str = "claude-code"


class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    platform: str
    capabilities: Optional[dict] = None
    status: WorkerStatus
    current_task_id: Optional[uuid.UUID] = None
    executor_type: str
    registered_at: datetime
    last_heartbeat: Optional[datetime] = None


class WorkerHeartbeatResponse(BaseModel):
    status: WorkerStatus
    pending_tasks: int


# ── Board Schemas ─────────────────────────────────────────────────────


class BoardColumn(BaseModel):
    tasks: list[TaskResponse]


class BoardResponse(BaseModel):
    project_id: uuid.UUID
    columns: dict[str, BoardColumn]
    stats: dict[str, int]


# ── Common Schemas ────────────────────────────────────────────────────


class SignedPrompt(BaseModel):
    prompt: str
    signature: str
    nonce: str
    timestamp: datetime


class TransitionResponse(BaseModel):
    task_id: uuid.UUID
    status: TaskStatus
    previous_status: TaskStatus
    transition: dict


# ── Architect Schemas ────────────────────────────────────────────────


class DesignSessionStatus(str, enum.Enum):
    active = "active"
    finalized = "finalized"
    cancelled = "cancelled"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class LLMConfigInput(BaseModel):
    api_key: str
    model: Optional[str] = None
    base_url: Optional[str] = None


class CreateSessionRequest(BaseModel):
    llm_config: LLMConfigInput


class MessageRequest(BaseModel):
    content: str


class DesignMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime


class DesignSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    status: DesignSessionStatus
    created_at: datetime
    updated_at: datetime
    messages: list[DesignMessageResponse] = Field(default_factory=list)


class FinalizeRequest(BaseModel):
    repo_path: str
    pm_llm_config: Optional[LLMConfigInput] = None


class AddTaskRequest(BaseModel):
    phase_id: uuid.UUID
    request_text: str
    llm_config: Optional[LLMConfigInput] = None


class AddTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    priority: TaskPriority
    worker_prompt: Optional[dict] = None
    qa_prompt: Optional[dict] = None
