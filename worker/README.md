# BSNexus Worker

Distributed worker agent that executes tasks assigned by the BSNexus backend.
Works like GitLab Runner: register once, run anytime.

## Setup

```bash
cd worker
uv pip install -e ".[dev]"
```

## Quick Start

1. Go to the BSNexus admin UI → **Workers** → **Registration Token**
2. Copy the generated CLI command
3. Register the worker (one-time):

```bash
bsnexus-worker register \
  --url http://<SERVER_HOST>:8000 \
  --token glrt-<YOUR_TOKEN> \
  --redis-url redis://<REDIS_HOST>:6379 \
  --executor claude-code
```

4. Start listening for tasks:

```bash
bsnexus-worker run
```

## CLI Commands

### `register` — Register and save credentials

Registers the worker with the server and saves credentials to `worker/.env`.
Exits immediately after registration.

```bash
bsnexus-worker register \
  --url <server-url>        # Required: BSNexus backend URL
  --token <reg-token>       # Required: Registration token from admin UI
  --redis-url <redis-url>   # Optional: Redis URL (default: redis://localhost:6379)
  --executor <type>         # Optional: Executor type (default: claude-code)
  --name <name>             # Optional: Worker display name (auto-generated)
```

### `run` — Start worker loop

Starts the worker using saved credentials from `worker/.env`.
Requires prior registration via `register`.

```bash
bsnexus-worker run \
  --duration <seconds>      # Optional: Max run time (default: infinite)
```

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
| `BSNEXUS_WORKER_ID` | Worker ID (auto-saved by `register`) | — |
| `BSNEXUS_WORKER_TOKEN` | Worker auth token (auto-saved by `register`) | — |

Copy `.env.example` to `.env` and fill in the values for your environment.

## Executor Types

- **`claude-code`** — Executes tasks using Claude Code CLI (default)
- Extensible: implement the executor interface for custom executors

## How It Works

1. `register`: Worker registers with the backend via `/api/v1/workers/register`, credentials saved to `.env`
2. `run`: Worker connects to Redis using saved credentials and listens on Streams for task assignments
3. Executes assigned tasks using the configured executor
4. Reports results back via Redis Streams
5. Sends periodic heartbeats to maintain active status
