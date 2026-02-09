from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Base repository with common database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, entity: Any) -> Any:
        """Add an entity and flush to get the ID."""
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.db.commit()

    async def refresh(self, entity: Any) -> None:
        """Refresh an entity instance from the database."""
        await self.db.refresh(entity)
