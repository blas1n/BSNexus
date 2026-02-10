from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.src.models import DesignMessage, DesignSession, DesignSessionStatus, MessageRole
from backend.src.repositories.design_session_repository import DesignSessionRepository


LLM_CONFIG = {"api_key": "sk-test-key", "model": "gpt-4o"}


async def _create_session(db_session) -> DesignSession:
    """Helper to create a design session directly in DB."""
    now = datetime.now(timezone.utc)
    session = DesignSession(
        id=uuid.uuid4(),
        status=DesignSessionStatus.active,
        llm_config=LLM_CONFIG,
        created_at=now,
        updated_at=now,
    )
    db_session.add(session)
    await db_session.flush()
    return session


async def _create_session_with_message(db_session) -> DesignSession:
    """Helper to create a session with one assistant message."""
    session = await _create_session(db_session)
    now = datetime.now(timezone.utc)
    msg = DesignMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role=MessageRole.assistant,
        content="System prompt",
        created_at=now,
    )
    db_session.add(msg)
    await db_session.commit()
    return session


class TestGetById:
    """Tests for DesignSessionRepository.get_by_id."""

    async def test_get_by_id_with_messages(self, db_session):
        """Retrieves a session with messages loaded by default."""
        session = await _create_session_with_message(db_session)

        repo = DesignSessionRepository(db_session)
        loaded = await repo.get_by_id(session.id)

        assert loaded is not None
        assert loaded.id == session.id
        assert loaded.status == DesignSessionStatus.active
        assert len(loaded.messages) == 1
        assert loaded.messages[0].role == MessageRole.assistant
        assert loaded.messages[0].content == "System prompt"

    async def test_get_by_id_without_messages(self, db_session):
        """Retrieves a session without eagerly loading messages."""
        session = await _create_session_with_message(db_session)

        repo = DesignSessionRepository(db_session)
        loaded = await repo.get_by_id(session.id, load_messages=False)

        assert loaded is not None
        assert loaded.id == session.id
        assert loaded.status == DesignSessionStatus.active

    async def test_get_by_id_not_found(self, db_session):
        """Returns None for a nonexistent session ID."""
        repo = DesignSessionRepository(db_session)
        loaded = await repo.get_by_id(uuid.uuid4())

        assert loaded is None


class TestAddMessage:
    """Tests for DesignSessionRepository.add_message."""

    async def test_add_message(self, db_session):
        """Adds a message and verifies it is persisted."""
        session = await _create_session(db_session)
        await db_session.commit()

        repo = DesignSessionRepository(db_session)
        msg = await repo.add_message(session.id, MessageRole.user, "Hello architect")
        await repo.commit()

        assert msg.session_id == session.id
        assert msg.role == MessageRole.user
        assert msg.content == "Hello architect"
        assert msg.id is not None

        # Verify it's retrievable via get_by_id
        loaded = await repo.get_by_id(session.id)
        assert loaded is not None
        user_msgs = [m for m in loaded.messages if m.role == MessageRole.user]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "Hello architect"

    async def test_add_multiple_messages(self, db_session):
        """Adds multiple messages and verifies all are persisted."""
        session = await _create_session(db_session)
        await db_session.commit()

        repo = DesignSessionRepository(db_session)
        await repo.add_message(session.id, MessageRole.user, "Question 1")
        await repo.add_message(session.id, MessageRole.assistant, "Answer 1")
        await repo.add_message(session.id, MessageRole.user, "Question 2")
        await repo.commit()

        loaded = await repo.get_by_id(session.id)
        assert loaded is not None
        assert len(loaded.messages) == 3


class TestAddAndCommit:
    """Tests for DesignSessionRepository.add and commit."""

    async def test_add_and_commit(self, db_session):
        """Adds a session via repo, commits, and re-queries."""
        repo = DesignSessionRepository(db_session)
        session = await repo.add(DesignSession(llm_config=LLM_CONFIG))
        await repo.commit()

        # Re-query to ensure it was persisted
        loaded = await repo.get_by_id(session.id)
        assert loaded is not None
        assert loaded.id == session.id
        assert loaded.llm_config == LLM_CONFIG

    async def test_add_session_and_message_workflow(self, db_session):
        """Full workflow: add session, add message, commit, and retrieve."""
        repo = DesignSessionRepository(db_session)
        session = await repo.add(DesignSession(llm_config=LLM_CONFIG))
        await repo.add_message(session.id, MessageRole.assistant, "Welcome!")
        await repo.commit()

        loaded = await repo.get_by_id(session.id)
        assert loaded is not None
        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "Welcome!"


class TestRefresh:
    """Tests for DesignSessionRepository.refresh."""

    async def test_refresh_entity(self, db_session):
        """Refresh reloads entity state from the database."""
        repo = DesignSessionRepository(db_session)
        session = await repo.add(DesignSession(llm_config=LLM_CONFIG))
        await repo.commit()

        msg = await repo.add_message(session.id, MessageRole.assistant, "Test message")
        await repo.commit()
        await repo.refresh(msg)

        assert msg.id is not None
        assert msg.content == "Test message"
