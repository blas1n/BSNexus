from __future__ import annotations

from fastapi import FastAPI


async def start_background_consumer(app: FastAPI) -> None:
    """Initialize orchestrators dict on app state at startup."""
    app.state.orchestrators = {}
