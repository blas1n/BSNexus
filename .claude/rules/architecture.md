# Architecture Rules

BSNexus is a FastAPI-based monolithic backend application.

## Core Stack

- **Runtime**: Python 3.11+ only
- **Framework**: FastAPI (async/await throughout)
- **Database**: PostgreSQL + SQLAlchemy 2.0 (async) + Alembic migrations
- **Queue**: Redis Streams (consumer group based, not Pub/Sub)
- **LLM**: LiteLLM (provider-agnostic LLM integration)
- **Config**: Pydantic BaseSettings + `.env` files
- **Dependencies**: pyproject.toml + uv (no requirements.txt)
- **Linting**: ruff (line-length 120)

## MUST Rules

### Architecture

- MUST: Monolithic structure — serve all APIs from a single FastAPI app
- MUST: Use type hints on all functions and methods
- MUST: Use async/await by default (no synchronous blocking calls)
- MUST: Define all request/response schemas with Pydantic models

### Redis Streams

- MUST: Use Redis Streams for message queuing (not Redis Pub/Sub)
- MUST: Follow consumer group pattern
- MUST: Serialize messages as JSON
- MUST: Acknowledge processed messages with `XACK`

```python
# CORRECT: Redis Streams with consumer groups
await stream_manager.publish("tasks:queue", {"task_id": task_id, "action": "execute"})
messages = await stream_manager.consume("tasks:queue", "workers", "worker-1")
await stream_manager.acknowledge("tasks:queue", "workers", msg_id)

# WRONG: Redis Pub/Sub
await redis.publish("tasks", message)  # Do not use Pub/Sub
```

### LiteLLM

- MUST: All LLM calls go through LiteLLM (no direct provider SDK calls)
- MUST: Inject model names from settings (no hardcoding)

```python
# CORRECT: Use LiteLLM
from litellm import acompletion

response = await acompletion(
    model=settings.default_llm_model,
    messages=[{"role": "user", "content": prompt}],
)

# WRONG: Direct provider call
from openai import AsyncOpenAI  # Do not use directly
```

### FastAPI Patterns

- MUST: Organize APIs into routers by module
- MUST: Use Dependency Injection for DB sessions, Redis, etc.
- MUST: Manage startup/shutdown with lifespan context manager

```python
# CORRECT: FastAPI router with dependency injection
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

@router.get("/{task_id}")
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)) -> TaskResponse:
    ...

# WRONG: Direct global state access
@router.get("/{task_id}")
async def get_task(task_id: int):
    async with global_session() as db:  # Not using DI
        ...
```

### Configuration

- MUST: Validate all environment variables with Pydantic BaseSettings
- MUST: Manage secrets via environment variables only (no hardcoding in code)
- MUST: Document all config keys in `.env.example`

```python
# CORRECT: Pydantic Settings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    database_url: str
    default_llm_model: str = "gpt-4o"

    model_config = SettingsConfigDict(env_file=".env")
```

### Data & Money

- MUST: Use `Decimal` type for monetary values (no float)

```python
# CORRECT
from decimal import Decimal
price: Decimal = Decimal("99.99")

# WRONG
price: float = 99.99
```

## NEVER Rules

- NEVER: Use `sys.path.insert` or `sys.path.append`
- NEVER: Use `requirements.txt` — use `pyproject.toml` + `uv`
- NEVER: Create per-service Dockerfiles (managed via docker-compose)
- NEVER: Hardcode secrets or API keys in code
- NEVER: Use f-strings in raw SQL queries (SQL injection risk)
- NEVER: Include `Co-Authored-By` in commit messages
- NEVER: Use `float` for monetary values
- NEVER: Use Redis Pub/Sub for message queuing (use Redis Streams)
- NEVER: Call LLM provider SDKs directly (use LiteLLM)
- NEVER: Use synchronous blocking I/O (use async/await)
- NEVER: Use gRPC, Redpanda, or Kong Gateway (legacy stack)

## Testing

- All code must have tests (>=80% coverage)
- Use `pytest` + `pytest-asyncio`
- See `.claude/rules/testing.md` for detailed rules

## Security

- See `.claude/rules/security.md` for detailed security rules
