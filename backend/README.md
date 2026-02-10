# BSNexus Backend

FastAPI async monolith serving all BSNexus APIs.

## Setup

```bash
cd backend
uv pip install -e ".[dev]"
```

## Running

```bash
uvicorn backend.src.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

| Prefix | Description |
|--------|------------|
| `/api/projects` | Project and phase CRUD |
| `/api/tasks` | Task CRUD and state transitions |
| `/api/workers` | Worker registration and heartbeat |
| `/api/board` | Kanban board state and events |
| `/api/architect` | Design session chat (HTTP + WebSocket) |
| `/api/pm` | PM orchestration control |
| `/health` | Health check endpoints |

API docs: http://localhost:8000/docs

## Testing

```bash
# All tests with coverage
python -m pytest tests/ -v --cov=src --cov-fail-under=80

# Integration tests only
python -m pytest tests/integration/ -v

# Lint
ruff check src/
```

## Key Modules

- **`core/state_machine.py`** - Task state machine with dependency resolution
- **`core/orchestrator.py`** - PM orchestration logic
- **`queue/streams.py`** - Redis Streams consumer group management
- **`storage/database.py`** - Async SQLAlchemy session factory
