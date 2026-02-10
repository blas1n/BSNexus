# BSNexus Frontend

React + TypeScript frontend for BSNexus.

## Setup

```bash
cd frontend
pnpm install
```

## Development

```bash
pnpm dev      # Start dev server on port 3000
pnpm build    # Production build
pnpm lint     # ESLint check
```

## Tech Stack

- React 19 + TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- React Router v7 (routing)
- Zustand (state management)
- TanStack Query (server state)
- Axios (HTTP client)

## Pages

| Path | Page | Description |
|------|------|------------|
| `/` | Dashboard | Project list and overview |
| `/architect/:sessionId?` | Architect | LLM design chat with WebSocket streaming |
| `/board/:projectId` | Board | Real-time Kanban board |
| `/workers` | Workers | Worker status and management |

## Environment

Copy `.env.example` and configure:

```bash
cp .env.example .env.local
```

| Variable | Description | Default |
|----------|-----------|---------|
| `VITE_API_URL` | Backend API URL | (empty, uses Vite proxy) |
