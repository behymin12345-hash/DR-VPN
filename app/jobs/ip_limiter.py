"""Per-user IP limit enforcement.

The node bridge has no native IP-limit hook, so the panel enforces it the
classic way: every interval it counts each limited user's distinct online IPs
across all nodes. Over the limit -> user is disabled (and tagged); once the
extra IPs drop, the user is re-enabled automatically. Only users tagged with
IP_LIMIT_NOTE_TAG are ever auto-enabled, so manual disables are never undone.
"""

from datetime import UTC, datetime as dt, timedelta as td

from sqlalchemy import select

from app import scheduler
from app.db import GetDB
from app.db.models import User, UserStatus
from app.jobs.dependencies import SYSTEM_ADMIN
from app.models.user import UserStatusToggle
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.operation.user import UserOperation
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("jobs")

IP_LIMIT_NOTE_TAG = "[ip-limit]"

node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)
user_operator = UserOperation(operator_type=OperatorType.SYSTEM)


def _distinct_ips(ip_lists) -> int:
    ips: set[str] = set()
    for node_list in (ip_lists.nodes or {}).values():
        if node_list and node_list.ips:
            ips.update(node_list.ips.keys())
    return len(ips)


async def run_ip_limiter():
    async with GetDB() as db:
        rows = (
            (
                await db.execute(
                    select(User.id, User.username, User.ip_limit, User.status, User.note).where(
                        User.ip_limit.is_not(None)
                    )
                )
            )
            .all()
        )
    if not rows:
        return

    for user_id, username, ip_limit, status, note in rows:
        if status not in (UserStatus.active, UserStatus.disabled):
            continue
        is_limiter_ban = IP_LIMIT_NOTE_TAG in (note or "")
        if status == UserStatus.disabled and not is_limiter_ban:
            continue  # manually disabled — never touch it

        async with GetDB() as db:
            db_user = await db.get(User, user_id)
            if db_user is None:
                continue
            try:
                ip_lists = await node_operator.get_user_ip_list_all_nodes(db, user_id)
            except Exception as exc:
                logger.debug("Could not fetch IP list for %s: %s", username, exc)
                continue
            distinct = _distinct_ips(ip_lists)

            if db_user.status == UserStatus.active and distinct > (ip_limit or 0):
                if IP_LIMIT_NOTE_TAG not in (db_user.note or ""):
                    db_user.note = f"{db_user.note or ''} {IP_LIMIT_NOTE_TAG}".strip()[:500]
                    await db.commit()
                await user_operator._set_user_disabled(
                    db, db_user, UserStatusToggle(disabled=True), SYSTEM_ADMIN
                )
                logger.info(
                    'User "%s" hit the IP limit (%d > %s) — disabled until IPs drop',
                    username,
                    distinct,
                    ip_limit,
                )
            elif db_user.status == UserStatus.disabled and IP_LIMIT_NOTE_TAG in (db_user.note or "") and distinct <= (
                ip_limit or 0
            ):
                db_user.note = (db_user.note or "").replace(IP_LIMIT_NOTE_TAG, "").strip()
                await db.commit()
                await user_operator._set_user_disabled(
                    db, db_user, UserStatusToggle(disabled=False), SYSTEM_ADMIN
                )
                logger.info(
                    'User "%s" back under the IP limit (%d <= %s) — re-enabled',
                    username,
                    distinct,
                    ip_limit,
                )


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        run_ip_limiter,
        "interval",
        seconds=job_settings.ip_limiter_interval,
        coalesce=True,
        start_date=dt.now(UTC) + td(minutes=1),
        max_instances=1,
        id="ip_limiter",
        replace_existing=True,
    )
