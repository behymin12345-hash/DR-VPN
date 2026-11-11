from fastapi import APIRouter, Depends, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.mtproto import (
    MtprotoProxyCreate,
    MtprotoProxyModify,
    MtprotoProxyResponse,
)
from app.models.proxy_clients import ProxyClientCreate, ProxyClientModify
from app.models.user import UserResponse, UsersResponse
from app.operation.mtproto import mtproto_proxy_operator
from app.operation.proxy_clients import proxy_clients_operator
from app.utils import responses

from .authentication import require_permission

router = APIRouter(
    tags=["MTProto Proxy"],
    prefix="/api/mtproto_proxy",
    responses={401: responses._401, 403: responses._403},
)

mtproto_operator = mtproto_proxy_operator
clients_operator = proxy_clients_operator


@router.get("", response_model=list[MtprotoProxyResponse])
async def get_mtproto_proxies(
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mtproto", "read")),
):
    return await mtproto_operator.get_mtproto_proxies(db, admin)


@router.post("", response_model=MtprotoProxyResponse, status_code=status.HTTP_201_CREATED)
async def create_mtproto_proxy(
    new_proxy: MtprotoProxyCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mtproto", "create")),
):
    return await mtproto_operator.create_mtproto_proxy(db, new_proxy, admin)


@router.put("/{proxy_id}", response_model=MtprotoProxyResponse)
async def modify_mtproto_proxy(
    proxy_id: int,
    modified: MtprotoProxyModify,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mtproto", "update")),
):
    return await mtproto_operator.modify_mtproto_proxy(db, proxy_id, modified, admin)


@router.delete("/{proxy_id}", response_model=MtprotoProxyResponse)
async def remove_mtproto_proxy(
    proxy_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mtproto", "delete")),
):
    return await mtproto_operator.remove_mtproto_proxy(db, proxy_id, admin)


# ---------------------------------------------------------------------------
# Proxy clients — users of proxy-only groups, managed with mtproto permissions
# ---------------------------------------------------------------------------


@router.get("/clients", response_model=UsersResponse)
async def get_proxy_clients(
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mtproto", "read")),
):
    """Users that belong exclusively to proxy groups (the proxy workspace roster)."""
    return await clients_operator.list_clients(db, admin)


@router.post("/clients", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_proxy_client(
    new_client: ProxyClientCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mtproto", "create")),
):
    return await clients_operator.create_client(
        db,
        new_client.username,
        admin,
        group_ids=new_client.group_ids,
        data_limit=new_client.data_limit,
        expire=new_client.expire,
        usage_coefficient=new_client.usage_coefficient,
        note=new_client.note,
    )


@router.put("/clients/{username}", response_model=UserResponse)
async def modify_proxy_client(
    username: str,
    modified: ProxyClientModify,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mtproto", "update")),
):
    return await clients_operator.modify_client(
        db,
        username,
        admin,
        group_ids=modified.group_ids,
        data_limit=modified.data_limit,
        expire=modified.expire,
        usage_coefficient=modified.usage_coefficient,
        note=modified.note,
        status=modified.status,
    )


@router.delete("/clients/{username}")
async def remove_proxy_client(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mtproto", "delete")),
):
    await clients_operator.remove_client(db, username, admin)
    return {}
