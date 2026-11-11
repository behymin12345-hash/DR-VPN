"""Proxy-workspace client management.

Clients are regular users that belong exclusively to "proxy groups" (groups
with no inbounds). The whole feature is gated by the mtproto resource
permission, so a proxy operator manages their own clients from the proxy page
without ever gaining general users.* access — config-side users stay invisible.
"""

import asyncio

from app.db import AsyncSession
from app.db.crud.group import get_group
from app.db.crud.user import get_user, get_users
from app.db.models import UserStatus
from app.models.admin import AdminDetails
from app.models.group import GroupListQuery
from app.models.user import UserCreate, UserListQuery, UserModify, UsersResponse
from app.operation import BaseOperation, OperatorType
from app.operation.user import UserOperation
from app.utils.logger import get_logger

logger = get_logger("proxy-clients")

user_operator = UserOperation(operator_type=OperatorType.API)


class ProxyClientsOperation(BaseOperation):
    async def proxy_group_ids(self, db: AsyncSession) -> list[int]:
        """Groups with no inbounds are proxy-only groups."""
        groups, _ = await get_group(db, GroupListQuery())
        return [g.id for g in groups if not g.inbound_tags]

    async def _assert_client(self, db: AsyncSession, username: str, proxy_ids: list[int]):
        db_user = await get_user(db, username)
        if db_user is None or not db_user.groups or not all(g.id in proxy_ids for g in db_user.groups):
            await self.raise_error(message=f"Proxy client \"{username}\" not found", code=404, db=db)
        return db_user

    async def _filter_to_proxy_groups(self, db: AsyncSession, group_ids: list[int] | None) -> list[int]:
        """Keep only proxy groups; an empty/None selection defaults to all proxy groups."""
        proxy_ids = await self.proxy_group_ids(db)
        if not proxy_ids:
            await self.raise_error(message="No proxy group exists — create one first", code=400, db=db)
        if not group_ids:
            return proxy_ids
        invalid = [gid for gid in group_ids if gid not in proxy_ids]
        if invalid:
            await self.raise_error(message="Clients may only belong to proxy groups", code=400, db=db)
        return group_ids

    async def list_clients(self, db: AsyncSession, admin: AdminDetails) -> UsersResponse:
        proxy_ids = await self.proxy_group_ids(db)
        if not proxy_ids:
            return UsersResponse(users=[], total=0)
        users, count = await get_users(
            db=db,
            query=UserListQuery(group_ids=proxy_ids, load_sub=False),
            return_with_count=True,
            load_usage_logs=False,
            load_lifetime_used_traffic=False,
        )
        urls = await asyncio.gather(*[user_operator.generate_subscription_url(user) for user in users])
        for user, url in zip(users, urls):
            user.subscription_url = url
        return UsersResponse(users=users, total=count)

    async def create_client(
        self,
        db: AsyncSession,
        username: str,
        admin: AdminDetails,
        *,
        group_ids: list[int] | None = None,
        data_limit: int | None = None,
        expire: int | None = None,
        usage_coefficient: float | None = None,
        note: str | None = None,
    ):
        group_ids = await self._filter_to_proxy_groups(db, group_ids)
        new_user = UserCreate(
            username=username,
            group_ids=group_ids,
            data_limit=data_limit,
            expire=expire,
            usage_coefficient=usage_coefficient if usage_coefficient is not None else 1.0,
            note=note,
            status=UserStatus.active,
        )
        # skip_role_limits: the router already gated this call behind the
        # mtproto resource; proxy operators do not carry users.* permissions.
        return await user_operator.create_user(db, new_user, admin, skip_role_limits=True)

    async def modify_client(
        self,
        db: AsyncSession,
        username: str,
        admin: AdminDetails,
        *,
        group_ids: list[int] | None = None,
        data_limit: int | None = None,
        expire: int | None = None,
        usage_coefficient: float | None = None,
        note: str | None = None,
        status: str | None = None,
    ):
        proxy_ids = await self.proxy_group_ids(db)
        db_user = await self._assert_client(db, username, proxy_ids)
        merged_group_ids: list[int] | None = None
        if group_ids is not None:
            if not group_ids:
                merged_group_ids = proxy_ids
            else:
                invalid = [gid for gid in group_ids if gid not in proxy_ids]
                if invalid:
                    await self.raise_error(message="Clients may only belong to proxy groups", code=400, db=db)
                merged_group_ids = group_ids
        modified = UserModify(
            group_ids=merged_group_ids,
            data_limit=data_limit,
            expire=expire,
            usage_coefficient=usage_coefficient,
            note=note,
            status=UserStatus(status) if status else None,
        )
        return await user_operator._modify_user(db, db_user, modified, admin, skip_role_limits=True)

    async def remove_client(self, db: AsyncSession, username: str, admin: AdminDetails):
        proxy_ids = await self.proxy_group_ids(db)
        db_user = await self._assert_client(db, username, proxy_ids)
        return await user_operator._remove_user(db, db_user, admin)


proxy_clients_operator = ProxyClientsOperation(OperatorType.API)
