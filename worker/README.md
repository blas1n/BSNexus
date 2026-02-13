# BSNexus Worker

Distributed worker agent that executes tasks assigned by the BSNexus backend.

## Setup

```bash
cd worker
uv pip install -e ".[dev]"
```

## Quick Start

1. Go to the BSNexus admin UI → **Workers** → **Registration Token**
2. Copy the generated CLI command
3. Run it on the worker machine:

```bash
bsnexus-worker register \
  --url http://<SERVER_HOST>:8000 \
  --token glrt-<YOUR_TOKEN> \
  --redis-url redis://<REDIS_HOST>:6379 \
  --executor claude-code
```

The worker will register, connect to Redis, and start listening for tasks.

## CLI Commands

### `register` — Register and start

```bash
bsnexus-worker register \
  --url <server-url>        # Required: BSNexus backend URL
  --token <reg-token>       # Required: Registration token from admin UI
  --redis-url <redis-url>   # Optional: Redis URL (default: redis://localhost:6379)
  --executor <type>         # Optional: Executor type (default: claude-code)
  --name <name>             # Optional: Worker display name (auto-generated)
  --duration <seconds>      # Optional: Max run time (default: infinite)
```

### `run` — Start with environment config

```bash
bsnexus-worker run \
  --server <server-url>     # Optional: BSNexus backend URL (default: http://localhost:8000)
  --duration <seconds>      # Optional: Max run time (default: infinite)
```

Uses `BSNEXUS_*` environment variables or `.env` file for configuration.

## Configuration

Environment variables (prefix `BSNEXUS_`):

| Variable | Description | Default |
|----------|-----------|---------|
| `BSNEXUS_SERVER_URL` | Backend API URL | `http://localhost:8000` |
| `BSNEXUS_REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `BSNEXUS_REGISTRATION_TOKEN` | Registration token | — |
| `BSNEXUS_WORKER_NAME` | Worker display name | auto-generated |
| `BSNEXUS_EXECUTOR_TYPE` | Executor type | `claude-code` |
| `BSNEXUS_HEARTBEAT_INTERVAL` | Heartbeat interval (seconds) | `30` |
| `BSNEXUS_DURATION` | Max run time (seconds) | infinite |

Copy `.env.example` to `.env` and fill in the values for your environment.

## Executor Types

- **`claude-code`** — Executes tasks using Claude Code CLI (default)
- Extensible: implement the executor interface for custom executors

## How It Works

1. Worker registers with the backend via `/api/v1/workers/register` (requires registration token)
2. Connects to Redis and listens on Streams for task assignments
3. Executes assigned tasks using the configured executor
4. Reports results back via Redis Streams
5. Sends periodic heartbeats to maintain active status
