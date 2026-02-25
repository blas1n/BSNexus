"""Tests for AccessController and permission system."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.access_control import (
    APIKey,
    AccessController,
    Permission,
    ROLE_PERMISSIONS,
    Role,
)


class TestAccessController:
    def test_generate_api_key_format(self):
        full_key, key_hash = AccessController.generate_api_key()
        assert full_key.startswith("bsn-")
        assert len(key_hash) == 64  # SHA-256 hex

    def test_generate_api_key_unique(self):
        key1, hash1 = AccessController.generate_api_key()
        key2, hash2 = AccessController.generate_api_key()
        assert key1 != key2
        assert hash1 != hash2

    def test_hash_key_consistent(self):
        hash1 = AccessController.hash_key("bsn-test-key")
        hash2 = AccessController.hash_key("bsn-test-key")
        assert hash1 == hash2

    def test_hash_key_different_keys(self):
        hash1 = AccessController.hash_key("bsn-key-one")
        hash2 = AccessController.hash_key("bsn-key-two")
        assert hash1 != hash2


class TestRolePermissions:
    def test_admin_has_all_permissions(self):
        assert ROLE_PERMISSIONS[Role.admin] == set(Permission)

    def test_viewer_has_read_only(self):
        viewer_perms = ROLE_PERMISSIONS[Role.viewer]
        assert Permission.project_read in viewer_perms
        assert Permission.task_read in viewer_perms
        assert Permission.board_read in viewer_perms
        assert Permission.project_create not in viewer_perms
        assert Permission.task_create not in viewer_perms
        assert Permission.admin_settings not in viewer_perms

    def test_operator_has_crud_but_not_admin(self):
        op_perms = ROLE_PERMISSIONS[Role.operator]
        assert Permission.project_create in op_perms
        assert Permission.task_create in op_perms
        assert Permission.admin_settings not in op_perms
        assert Permission.admin_security not in op_perms

    def test_worker_has_minimal_permissions(self):
        worker_perms = ROLE_PERMISSIONS[Role.worker]
        assert Permission.task_read in worker_perms
        assert Permission.task_transition in worker_perms
        assert Permission.project_create not in worker_perms


class TestHasPermission:
    def test_admin_has_any_permission(self):
        assert AccessController.has_permission(Role.admin, Permission.admin_security) is True
        assert AccessController.has_permission(Role.admin, Permission.project_create) is True

    def test_viewer_lacks_write_permissions(self):
        assert AccessController.has_permission(Role.viewer, Permission.project_create) is False
        assert AccessController.has_permission(Role.viewer, Permission.admin_settings) is False

    def test_viewer_has_read_permissions(self):
        assert AccessController.has_permission(Role.viewer, Permission.project_read) is True
        assert AccessController.has_permission(Role.viewer, Permission.board_read) is True


class TestGetPermissions:
    def test_returns_set(self):
        perms = AccessController.get_permissions(Role.viewer)
        assert isinstance(perms, set)

    def test_admin_returns_all(self):
        perms = AccessController.get_permissions(Role.admin)
        assert len(perms) == len(Permission)


class TestAPIKeyModel:
    async def test_create_api_key_in_db(self, db_session: AsyncSession):
        full_key, key_hash = AccessController.generate_api_key()
        api_key = APIKey(
            name="Test Key",
            key_hash=key_hash,
            key_prefix=full_key[:10],
            role=Role.admin,
        )
        db_session.add(api_key)
        await db_session.commit()

        result = await db_session.execute(select(APIKey).where(APIKey.key_hash == key_hash))
        stored = result.scalar_one()
        assert stored.name == "Test Key"
        assert stored.role == Role.admin
        assert stored.is_active is True

    async def test_api_key_with_expiry(self, db_session: AsyncSession):
        full_key, key_hash = AccessController.generate_api_key()
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        api_key = APIKey(
            name="Expiring Key",
            key_hash=key_hash,
            key_prefix=full_key[:10],
            role=Role.viewer,
            expires_at=expires,
        )
        db_session.add(api_key)
        await db_session.commit()

        result = await db_session.execute(select(APIKey).where(APIKey.key_hash == key_hash))
        stored = result.scalar_one()
        assert stored.expires_at is not None


class TestRequirePermissionBootstrap:
    """Test that bootstrap mode allows access when no API keys exist."""

    async def test_bootstrap_mode_allows_access(self, client):
        """When no API keys exist, access should be granted (bootstrap mode)."""
        resp = await client.get("/api/v1/security/api-keys")
        assert resp.status_code == 200
