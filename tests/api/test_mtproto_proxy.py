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
