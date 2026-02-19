"""Tests for AuditLogger."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.audit_logger import AuditAction, AuditLog, AuditLogger, AuditSeverity


async def test_log_creates_entry(db_session: AsyncSession):
    logger = AuditLogger(db_session)
    entry = await logger.log(
        AuditAction.data_created,
        actor_id="user-123",
        resource_type="project",
        resource_id="proj-456",
        details={"name": "Test Project"},
    )
    await db_session.commit()

    assert entry.id is not None
    assert entry.action == AuditAction.data_created
    assert entry.severity == AuditSeverity.info
    assert entry.actor_id == "user-123"
    assert entry.resource_type == "project"
    assert entry.details == {"name": "Test Project"}


async def test_log_persists_to_db(db_session: AsyncSession):
    logger = AuditLogger(db_session)
    await logger.log(
        AuditAction.auth_login,
        actor_id="admin-1",
        ip_address="192.168.1.1",
    )
    await db_session.commit()

    result = await db_session.execute(select(AuditLog))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].action == AuditAction.auth_login
    assert logs[0].ip_address == "192.168.1.1"


async def test_log_security_event_sets_warning_severity(db_session: AsyncSession):
    logger = AuditLogger(db_session)
    entry = await logger.log_security_event(
        AuditAction.security_rate_limited,
        ip_address="10.0.0.1",
        details={"path": "/api/v1/tasks"},
    )
    await db_session.commit()

    assert entry.severity == AuditSeverity.warning


async def test_log_security_event_critical_for_unauthorized(db_session: AsyncSession):
    logger = AuditLogger(db_session)
    entry = await logger.log_security_event(
        AuditAction.security_unauthorized,
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    assert entry.severity == AuditSeverity.critical


async def test_log_security_event_critical_for_tampered(db_session: AsyncSession):
    logger = AuditLogger(db_session)
    entry = await logger.log_security_event(
        AuditAction.security_prompt_tampered,
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    assert entry.severity == AuditSeverity.critical


async def test_log_data_access(db_session: AsyncSession):
    logger = AuditLogger(db_session)
    entry = await logger.log_data_access(
        AuditAction.data_read,
        actor_id="user-1",
        resource_type="task",
        resource_id="task-123",
        details={"fields": ["status", "description"]},
    )
    await db_session.commit()

    assert entry.action == AuditAction.data_read
    assert entry.resource_type == "task"
    assert entry.resource_id == "task-123"


async def test_multiple_log_entries(db_session: AsyncSession):
    logger = AuditLogger(db_session)
    await logger.log(AuditAction.auth_login, actor_id="user-1")
    await logger.log(AuditAction.data_created, actor_id="user-1", resource_type="project")
    await logger.log(AuditAction.auth_logout, actor_id="user-1")
    await db_session.commit()

    result = await db_session.execute(select(AuditLog))
    logs = result.scalars().all()
    assert len(logs) == 3
