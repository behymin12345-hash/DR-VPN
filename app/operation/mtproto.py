from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.mtproto import (
    create_mtproto_proxy,
    get_mtproto_proxies,
    get_mtproto_proxy,
    modify_mtproto_proxy,
    remove_mtproto_proxy,
)
from app.db.models import Admin, MtprotoProxy
from app.models.admin import AdminDetails
from app.models.mtproto import MtprotoProxyCreate, MtprotoProxyModify, MtprotoProxyResponse
from app.operation import BaseOperation, OperatorType


class MtprotoProxyOperation(BaseOperation):
    """Proxy management with reseller-style ownership: owners see and manage
    every proxy, regular admins only their own."""

    async def _visible_proxies(self, db: AsyncSession, admin: AdminDetails) -> list:
        if admin.is_owner:
            return await get_mtproto_proxies(db)
        result = await db.execute(
            select(MtprotoProxy).where(MtprotoProxy.admin_id == admin.id).order_by(MtprotoProxy.id.asc())
        )
        return list(result.scalars().all())

    async def create_mtproto_proxy(
        self, db: AsyncSession, data: MtprotoProxyCreate, admin: AdminDetails
    ) -> MtprotoProxyResponse:
        if not admin.is_owner:
            # regular admins always own the proxies they create
            data.admin_id = admin.id
        elif data.admin_id and not await self._admin_exists(db, data.admin_id):
            await self.raise_error("Admin not found", status.HTTP_404_NOT_FOUND, db)
        try:
            proxy = await create_mtproto_proxy(db, data)
        except IntegrityError:
            await self.raise_error("Proxy name already exists", status.HTTP_409_CONFLICT, db)
        return MtprotoProxyResponse.model_validate(proxy)

    async def get_mtproto_proxies(self, db: AsyncSession, admin: AdminDetails) -> list[MtprotoProxyResponse]:
        proxies = await self._visible_proxies(db, admin)
        return [MtprotoProxyResponse.model_validate(p) for p in proxies]

    async def _get_owned(self, db: AsyncSession, proxy_id: int, admin: AdminDetails):
        proxy = await get_mtproto_proxy(db, proxy_id)
        if not proxy:
            await self.raise_error("Proxy not found", status.HTTP_404_NOT_FOUND, db)
        if not admin.is_owner and proxy.admin_id != admin.id:
            await self.raise_error("Proxy not found", status.HTTP_404_NOT_FOUND, db)
        return proxy

    async def modify_mtproto_proxy(
        self, db: AsyncSession, proxy_id: int, data: MtprotoProxyModify, admin: AdminDetails
    ) -> MtprotoProxyResponse:
        proxy = await self._get_owned(db, proxy_id, admin)
        try:
            proxy = await modify_mtproto_proxy(db, proxy, data)
        except IntegrityError:
            await self.raise_error("Proxy name already exists", status.HTTP_409_CONFLICT, db)
        return MtprotoProxyResponse.model_validate(proxy)

    async def remove_mtproto_proxy(self, db: AsyncSession, proxy_id: int, admin: AdminDetails) -> MtprotoProxyResponse:
        proxy = await self._get_owned(db, proxy_id, admin)
        await remove_mtproto_proxy(db, proxy)
        return MtprotoProxyResponse.model_validate(proxy)

    async def _admin_exists(self, db: AsyncSession, admin_id: int) -> bool:
        return (await db.execute(select(Admin.id).where(Admin.id == admin_id))).scalar_one_or_none() is not None


mtproto_proxy_operator = MtprotoProxyOperation(OperatorType.API)
