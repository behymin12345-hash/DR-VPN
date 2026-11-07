from fastapi import APIRouter, Depends, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.mtproto import (
    MtprotoProxyCreate,
    MtprotoProxyModify,
    MtprotoProxyResponse,
)
from app.operation import OperatorType
from app.operation.mtproto import mtproto_proxy_operator
from app.utils import responses

from .authentication import require_permission

router = APIRouter(
    tags=["MTProto Proxy"],
    prefix="/api/mtproto_proxy",
    responses={401: responses._401, 403: responses._403},
)

mtproto_operator = mtproto_proxy_operator


@router.get("", response_model=list[MtprotoProxyResponse])
async def get_mtproto_proxies(
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("settings", "read")),
):
    return await mtproto_operator.get_mtproto_proxies(db, admin)


@router.post("", response_model=MtprotoProxyResponse, status_code=status.HTTP_201_CREATED)
async def create_mtproto_proxy(
    new_proxy: MtprotoProxyCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("settings", "update")),
):
    return await mtproto_operator.create_mtproto_proxy(db, new_proxy, admin)


@router.put("/{proxy_id}", response_model=MtprotoProxyResponse)
async def modify_mtproto_proxy(
    proxy_id: int,
    modified: MtprotoProxyModify,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("settings", "update")),
):
    return await mtproto_operator.modify_mtproto_proxy(db, proxy_id, modified, admin)


@router.delete("/{proxy_id}", response_model=MtprotoProxyResponse)
async def remove_mtproto_proxy(
    proxy_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("settings", "update")),
):
    return await mtproto_operator.remove_mtproto_proxy(db, proxy_id, admin)
