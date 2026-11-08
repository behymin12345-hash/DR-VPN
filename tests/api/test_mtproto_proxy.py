"""Tests for /api/mtproto_proxy CRUD."""

import uuid

from fastapi import status

from tests.api import client


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _unique(name: str) -> str:
    return f"{name}-{uuid.uuid4().hex[:8]}"


def test_create_list_modify_delete_mtproxy(access_token):
    headers = _auth(access_token)

    name = _unique("main-tg")
    created = client.post(
        "/api/mtproto_proxy",
        headers=headers,
        json={
            "name": name,
            "server": "5.6.7.8",
            "port": 443,
            "secret": "ee1a2b3c",
            "enabled": True,
        },
    )
    assert created.status_code == status.HTTP_201_CREATED
    body = created.json()
    assert body["name"] == name
    assert body["enabled"] is True
    proxy_id = body["id"]

    # duplicate name rejected
    dup = client.post(
        "/api/mtproto_proxy",
        headers=headers,
        json={"name": name, "server": "1.1.1.1", "port": 443, "secret": "ee", "enabled": False},
    )
    assert dup.status_code == status.HTTP_409_CONFLICT

    listed = client.get("/api/mtproto_proxy", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
    assert any(p["id"] == proxy_id for p in listed.json())

    modified = client.put(
        f"/api/mtproto_proxy/{proxy_id}",
        headers=headers,
        json={
            "name": name,
            "server": "5.6.7.8",
            "port": 8443,
            "secret": "ee1a2b3c",
            "enabled": False,
        },
    )
    assert modified.status_code == status.HTTP_200_OK
    assert modified.json()["port"] == 8443
    assert modified.json()["enabled"] is False

    removed = client.delete(f"/api/mtproto_proxy/{proxy_id}", headers=headers)
    assert removed.status_code == status.HTTP_200_OK

    missing = client.get("/api/mtproto_proxy", headers=headers)
    assert missing.status_code == status.HTTP_200_OK
    assert all(p["id"] != proxy_id for p in missing.json())


def test_modify_missing_mtproxy_404(access_token):
    headers = _auth(access_token)
    res = client.put(
        "/api/mtproto_proxy/999999",
        headers=headers,
        json={"name": _unique("x"), "server": "1.2.3.4", "port": 443, "secret": "s", "enabled": True},
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_create_mtproxy_validation_error(access_token):
    headers = _auth(access_token)
    res = client.post(
        "/api/mtproto_proxy",
        headers=headers,
        json={"name": "", "server": "1.1.1.1", "port": 70000, "secret": " ", "enabled": True},
    )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_admin_ownership_scoping(access_token):
    """Regular admins own the proxies they create and cannot touch others'."""
    import uuid

    name_a = f"owner-proxy-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/mtproto_proxy",
        headers=_auth(access_token),
        json={"name": name_a, "server": "1.1.1.1", "port": 443, "secret": "ee", "enabled": True},
    )
    assert created.status_code == status.HTTP_201_CREATED
    owner_proxy_id = created.json()["id"]

    role_res = client.post(
        "/api/admin-role",
        headers=_auth(access_token),
        json={
            "name": f"proxy-reseller-{uuid.uuid4().hex[:6]}",
            "permissions": {"settings": {"read": True, "update": True}},
        },
    )
    assert role_res.status_code == status.HTTP_201_CREATED, role_res.text
    role_id = role_res.json()["id"]
    creds = {
        "username": f"reseller-{uuid.uuid4().hex[:6]}",
        "password": "Reseller!2026XY",
        "role_id": role_id,
    }
    created_admin = client.post("/api/admin", headers=_auth(access_token), json=creds)
    assert created_admin.status_code == status.HTTP_201_CREATED, created_admin.text

    reseller_token_res = client.post(
        "/api/admin/token",
        data={"username": creds["username"], "password": creds["password"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert reseller_token_res.status_code == status.HTTP_200_OK
    reseller_token = reseller_token_res.json()["access_token"]
    reseller_headers = _auth(reseller_token)

    name_b = f"reseller-proxy-{uuid.uuid4().hex[:8]}"
    created_b = client.post(
        "/api/mtproto_proxy",
        headers=reseller_headers,
        json={
            "name": name_b,
            "server": "2.2.2.2",
            "port": 443,
            "secret": "ee",
            "enabled": True,
            "sponsored_channel": "@mychannel",
            "tag": "aabbccddeeff0011",
        },
    )
    assert created_b.status_code == status.HTTP_201_CREATED, created_b.text
    body_b = created_b.json()
    assert body_b["admin_id"] is not None
    assert body_b["sponsored_channel"] == "@mychannel"

    reseller_list = client.get("/api/mtproto_proxy", headers=reseller_headers)
    ids = [p["id"] for p in reseller_list.json()]
    assert created_b.json()["id"] in ids
    assert owner_proxy_id not in ids

    owner_list = client.get("/api/mtproto_proxy", headers=_auth(access_token))
    owner_ids = [p["id"] for p in owner_list.json()]
    assert owner_proxy_id in owner_ids
    assert created_b.json()["id"] in owner_ids

    mod_other = client.put(
        f"/api/mtproto_proxy/{owner_proxy_id}",
        headers=reseller_headers,
        json={"name": "hijacked", "server": "1.1.1.1", "port": 443, "secret": "ee", "enabled": True},
    )
    assert mod_other.status_code == status.HTTP_404_NOT_FOUND
    del_other = client.delete(f"/api/mtproto_proxy/{owner_proxy_id}", headers=reseller_headers)
    assert del_other.status_code == status.HTTP_404_NOT_FOUND

    del_own = client.delete(f"/api/mtproto_proxy/{created_b.json()['id']}", headers=reseller_headers)
    assert del_own.status_code == status.HTTP_200_OK

    client.delete(f"/api/mtproto_proxy/{owner_proxy_id}", headers=_auth(access_token))
