from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.mtproto import (
    create_mtproto_proxy,
    get_enabled_mtproto_proxies,
    get_mtproto_proxy,
    get_mtproto_proxies,
    modify_mtproto_proxy,
    remove_mtproto_proxy,
)
from app.models.admin import AdminDetails
from app.models.mtproto import MtprotoProxyCreate, MtprotoProxyModify, MtprotoProxyResponse
from app.operation import BaseOperation, OperatorType


class MtprotoProxyOperation(BaseOperation):
    async def create_mtproto_proxy(
        self, db: AsyncSession, data: MtprotoProxyCreate, _: AdminDetails
    ) -> MtprotoProxyResponse:
        try:
            proxy = await create_mtproto_proxy(db, data)
        except IntegrityError:
            await self.raise_error("Proxy name already exists", status.HTTP_409_CONFLICT, db)
        await db.refresh(proxy)
        return MtprotoProxyResponse.model_validate(proxy)

    async def get_mtproto_proxies(self, db: AsyncSession, _: AdminDetails) -> list[MtprotoProxyResponse]:
        proxies = await get_mtproto_proxies(db)
        return [MtprotoProxyResponse.model_validate(p) for p in proxies]

    async def modify_mtproto_proxy(
        self, db: AsyncSession, proxy_id: int, data: MtprotoProxyModify, _: AdminDetails
    ) -> MtprotoProxyResponse:
        proxy = await get_mtproto_proxy(db, proxy_id)
        if not proxy:
            await self.raise_error("Proxy not found", status.HTTP_404_NOT_FOUND, db)
        try:
            proxy = await modify_mtproto_proxy(db, proxy, data)
        except IntegrityError:
            await self.raise_error("Proxy name already exists", status.HTTP_409_CONFLICT, db)
        return MtprotoProxyResponse.model_validate(proxy)

    async def remove_mtproto_proxy(self, db: AsyncSession, proxy_id: int, _: AdminDetails) -> MtprotoProxyResponse:
        proxy = await get_mtproto_proxy(db, proxy_id)
        if not proxy:
            await self.raise_error("Proxy not found", status.HTTP_404_NOT_FOUND, db)
        await remove_mtproto_proxy(db, proxy)
        return MtprotoProxyResponse.model_validate(proxy)


mtproto_proxy_operator = MtprotoProxyOperation(OperatorType.API)
