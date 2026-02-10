from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.src.models import DesignMessage, DesignSession, MessageRole
from backend.src.repositories.base import BaseRepository


class DesignSessionRepository(BaseRepository):
    """Data access layer for DesignSession and DesignMessage entities."""

    async def get_by_id(self, session_id: uuid.UUID, *, load_messages: bool = True) -> DesignSession | None:
        """Get a session by ID with optional message loading."""
        query = select(DesignSession).where(DesignSession.id == session_id)
        if load_messages:
            query = query.options(selectinload(DesignSession.messages))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def add_message(self, session_id: uuid.UUID, role: MessageRole, content: str) -> DesignMessage:
        """Add a message to a session."""
        msg = DesignMessage(session_id=session_id, role=role, content=content)
        self.db.add(msg)
        await self.db.flush()
        return msg
