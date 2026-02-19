# BSNexus

AI-powered development management system. An LLM Architect designs your project, and distributed Worker nodes automatically write the code.

## Features

- **Architect** - LLM-based project design through interactive conversation
- **Task Engine** - Automated task decomposition with dependency-aware state machine
- **Worker System** - Distributed code execution via Claude Code (extensible to other executors)
- **Kanban Board** - Real-time task visualization with WebSocket updates
- **Git Automation** - Automatic branch, commit, and revert management per task

## Architecture

```
                    ┌──────────────┐
                    │   Frontend   │  React + Vite
                    │  (port 3000) │  TypeScript + Tailwind
                    └──────┬───────┘
                           │ HTTP / WebSocket
                    ┌──────┴───────┐
                    │   Backend    │  FastAPI (async)
                    │  (port 8000) │  SQLAlchemy 2.0
                    └──┬───────┬───┘
                       │       │
              ┌────────┴───┐ ┌──┴────────┐
              │ PostgreSQL │ │   Redis   │
              │  (storage) │ │ (streams) │
              └────────────┘ └─────┬─────┘
                                   │ Redis Streams
                           ┌───────┴───────┐
                           │    Workers    │
                           │ (Claude Code) │
                           └───────────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+ and pnpm
- An LLM API key (Anthropic, OpenAI, etc.)

### Setup

1. **Clone and configure**

   ```bash
   git clone <repository-url>
   cd bsnexus
   cp .env.example .env
   # Edit .env with your settings
   ```

2. **Start infrastructure**

   ```bash
   docker compose up -d postgres redis
   ```

3. **Start backend**

   ```bash
   cd backend
   uv pip install -e ".[dev]"
   uvicorn backend.src.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Start frontend**

   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```

5. **Register a Worker**

   ```bash
   cd worker
   uv pip install -e ".[dev]"
   python -m worker.main
   ```

6. **Open the app** at http://localhost:3000

## Tech Stack

| Layer        | Technology                                                        |
| ------------ | ----------------------------------------------------------------- |
| Frontend     | React 19, TypeScript, Vite, Tailwind CSS, Zustand, TanStack Query |
| Backend      | Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic            |
| Queue        | Redis Streams (consumer groups)                                   |
| Database     | PostgreSQL 16                                                     |
| LLM          | LiteLLM (provider-agnostic)                                       |
| Worker       | Claude Code (extensible executor system)                          |
| Package Mgmt | uv (Python), pnpm (Node.js)                                       |

## API Documentation

FastAPI auto-generated docs available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

### Backend tests

```bash
cd /workspace
python -m pytest backend/tests/ -v --cov=backend/src --cov-fail-under=80
```

### Frontend build

```bash
cd frontend
pnpm lint
pnpm build
```

### Linting

```bash
ruff check backend/src/ worker/src/
```

## Project Structure

```
bsnexus/
├── backend/              # FastAPI backend
│   ├── src/
│   │   ├── api/          # Route handlers
│   │   ├── core/         # Business logic (state machine, orchestrator)
│   │   ├── storage/      # Database & Redis
│   │   ├── queue/        # Redis Streams
│   │   └── main.py       # App entry point
│   └── tests/
├── frontend/             # React frontend
│   ├── src/
│   │   ├── api/          # API client modules
│   │   ├── components/   # UI components
│   │   ├── hooks/        # Custom hooks
│   │   ├── pages/        # Page components
│   │   ├── stores/       # Zustand stores
│   │   └── types/        # TypeScript types
│   └── package.json
├── worker/               # Worker agent
│   └── src/
├── docker-compose.yml    # Production compose
└── .env.example          # Environment template
```

## License

MIT
