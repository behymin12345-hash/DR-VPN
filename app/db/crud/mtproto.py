from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MtprotoProxy
from app.models.mtproto import MtprotoProxyCreate, MtprotoProxyModify


async def get_mtproto_proxy(db: AsyncSession, proxy_id: int) -> MtprotoProxy | None:
    try:
        return (
            await db.execute(select(MtprotoProxy).where(MtprotoProxy.id == proxy_id))
        ).scalar_one_or_none()
    except SQLAlchemyError:
        return None


async def get_mtproto_proxies(db: AsyncSession) -> list[MtprotoProxy]:
    try:
        return list(
            (
                await db.execute(select(MtprotoProxy).order_by(MtprotoProxy.id.asc()))
            ).scalars().all()
        )
    except SQLAlchemyError:
        return []


async def get_enabled_mtproto_proxies(db: AsyncSession) -> list[MtprotoProxy]:
    try:
        return list(
            (
                await db.execute(
                    select(MtprotoProxy)
                    .where(MtprotoProxy.enabled == True)  # noqa: E712
                    .order_by(MtprotoProxy.id.asc())
                )
            ).scalars().all()
        )
    except SQLAlchemyError:
        return []


async def create_mtproto_proxy(db: AsyncSession, data: MtprotoProxyCreate) -> MtprotoProxy:
    proxy = MtprotoProxy(**data.model_dump())
    db.add(proxy)
    await db.commit()
    await db.refresh(proxy)
    return proxy


async def modify_mtproto_proxy(
    db: AsyncSession, proxy: MtprotoProxy, data: MtprotoProxyModify
) -> MtprotoProxy:
    for field, value in data.model_dump().items():
        setattr(proxy, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(proxy)
    return proxy


async def remove_mtproto_proxy(db: AsyncSession, proxy: MtprotoProxy) -> None:
    await db.delete(proxy)
    await db.commit()
