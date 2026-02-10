# BSNexus Worker

Distributed worker agent that executes tasks assigned by the BSNexus backend.

## Setup

```bash
cd worker
uv pip install -e ".[dev]"
```

## Configuration

Environment variables (prefix `BSNEXUS_`):

| Variable | Description | Default |
|----------|-----------|---------|
| `BSNEXUS_SERVER_URL` | Backend API URL | `http://localhost:8000` |
| `BSNEXUS_REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `BSNEXUS_WORKER_NAME` | Worker display name | auto-generated |
| `BSNEXUS_EXECUTOR_TYPE` | Executor type | `claude-code` |
| `BSNEXUS_HEARTBEAT_INTERVAL` | Heartbeat interval (seconds) | `30` |

## Running

```bash
python -m worker.src.main
```

## Executor Types

- **`claude-code`** - Executes tasks using Claude Code CLI (default)
- Extensible: implement the executor interface for custom executors

## How It Works

1. Worker registers with the backend via `/api/workers/register`
2. Listens on Redis Streams for task assignments
3. Executes assigned tasks using the configured executor
4. Reports results back via Redis Streams
5. Sends periodic heartbeats to maintain active status
