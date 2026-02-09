from __future__ import annotations

import uuid

from sqlalchemy import func, select

from backend.src.models import Phase
from backend.src.repositories.base import BaseRepository


class PhaseRepository(BaseRepository):
    """Data access layer for Phase entities."""

    async def get_by_id(self, phase_id: uuid.UUID) -> Phase | None:
        """Get a phase by ID."""
        result = await self.db.execute(select(Phase).where(Phase.id == phase_id))
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: uuid.UUID) -> list[Phase]:
        """List phases for a project ordered by order."""
        result = await self.db.execute(select(Phase).where(Phase.project_id == project_id).order_by(Phase.order.asc()))
        return list(result.scalars().all())

    async def get_next_order(self, project_id: uuid.UUID) -> int:
        """Calculate the next order value for a project."""
        result = await self.db.execute(
            select(func.coalesce(func.max(Phase.order), 0)).where(Phase.project_id == project_id)
        )
        return result.scalar_one() + 1

