"""Tests for security API endpoints."""

from httpx import AsyncClient


async def test_security_scan_endpoint(client: AsyncClient):
    """Bootstrap mode: no API keys, so access is granted."""
    resp = await client.get("/api/v1/security/audit/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert "scan_timestamp" in data
    assert "passed" in data
    assert "summary" in data
    assert "findings" in data


async def test_audit_logs_endpoint(client: AsyncClient):
    resp = await client.get("/api/v1/security/audit/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


async def test_audit_logs_with_filters(client: AsyncClient):
    resp = await client.get("/api/v1/security/audit/logs", params={
        "action": "auth.login",
        "severity": "info",
        "limit": 10,
        "offset": 0,
    })
    assert resp.status_code == 200


async def test_compliance_report_endpoint(client: AsyncClient):
    resp = await client.get("/api/v1/security/compliance/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_status" in data
    assert "frameworks" in data
    assert "checks" in data


async def test_compliance_report_with_framework_filter(client: AsyncClient):
    resp = await client.get("/api/v1/security/compliance/report", params={"frameworks": "gdpr"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["frameworks"] == ["gdpr"]


async def test_compliance_report_invalid_framework(client: AsyncClient):
    resp = await client.get("/api/v1/security/compliance/report", params={"frameworks": "invalid"})
    assert resp.status_code == 400


async def test_create_api_key(client: AsyncClient):
    resp = await client.post("/api/v1/security/api-keys", json={
        "name": "Test Key",
        "role": "admin",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Key"
    assert data["role"] == "admin"
    assert data["key"].startswith("bsn-")
    assert "id" in data


async def test_create_api_key_with_expiry(client: AsyncClient):
    resp = await client.post("/api/v1/security/api-keys", json={
        "name": "Expiring Key",
        "role": "viewer",
        "expires_in_days": 30,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["expires_at"] is not None


async def test_create_api_key_invalid_role(client: AsyncClient):
    resp = await client.post("/api/v1/security/api-keys", json={
        "name": "Bad Key",
        "role": "superadmin",
    })
    assert resp.status_code == 400


async def test_list_api_keys(client: AsyncClient):
    # Create an admin key first (bootstrap mode allows this)
    create_resp = await client.post("/api/v1/security/api-keys", json={"name": "Admin Key", "role": "admin"})
    admin_key = create_resp.json()["key"]

    # Now list keys using the admin key for auth
    resp = await client.get(
        "/api/v1/security/api-keys",
        headers={"Authorization": f"Bearer {admin_key}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # Key should not expose full key
    for key in data:
        assert "key_prefix" in key


async def test_revoke_api_key(client: AsyncClient):
    # Create an admin key (bootstrap mode)
    admin_resp = await client.post("/api/v1/security/api-keys", json={"name": "Admin Key", "role": "admin"})
    admin_key = admin_resp.json()["key"]
    auth_headers = {"Authorization": f"Bearer {admin_key}"}

    # Create a viewer key to revoke
    create_resp = await client.post(
        "/api/v1/security/api-keys",
        json={"name": "Revoke Test", "role": "viewer"},
        headers=auth_headers,
    )
    key_id = create_resp.json()["id"]

    # Revoke it
    resp = await client.delete(f"/api/v1/security/api-keys/{key_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify it shows as inactive
    list_resp = await client.get("/api/v1/security/api-keys", headers=auth_headers)
    keys = list_resp.json()
    revoked_key = next(k for k in keys if k["id"] == key_id)
    assert revoked_key["is_active"] is False


async def test_revoke_nonexistent_key(client: AsyncClient):
    import uuid

    resp = await client.delete(f"/api/v1/security/api-keys/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_encryption_test_endpoint(client: AsyncClient):
    resp = await client.post("/api/v1/security/encrypt-test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["encrypted_length"] > 0
