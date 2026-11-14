import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import AsyncSession, get_db
from app.db.crud.wireguard import get_subnet_usage
from app.models.admin import AdminDetails
from app.models.settings import Telegram
from app.models.system import (
    InboundSummary,
    SystemResourceStats,
    SystemStats,
    SystemUsersStats,
    WireGuardSubnetUsage,
    WorkerHealth,
    WorkersHealth,
)
from app.nats import is_nats_enabled
from app.nats.node_rpc import node_nats_client
from app.nats.scheduler_rpc import scheduler_nats_client
from app.operation import OperatorType
from app.operation.system import SystemOperation
from app.settings import telegram_settings
from app.telegram import get_bot, get_dispatcher
from app.utils import responses
from app.utils.logger import EndpointFilter, get_logger
from config import telegram_env_settings

from .authentication import require_permission

system_operator = SystemOperation(operator_type=OperatorType.API)
router = APIRouter(tags=["System"], prefix="/api", responses={401: responses._401})

TELEGRAM_WEBHOOK_PATH = "/tghook"
if telegram_env_settings.do_not_log_bot:
    uvicorn_access_logger = get_logger("uvicorn.access")
    uvicorn_access_logger.addFilter(EndpointFilter([f"{router.prefix}{TELEGRAM_WEBHOOK_PATH}"]))


@router.get("/system", response_model=SystemStats)
async def get_system_stats(
    admin_username: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("system", "read")),
):
    """Fetch system stats including memory, CPU, disk, and user metrics."""
    return await system_operator.get_system_stats(db, admin=admin, admin_username=admin_username)


@router.get("/system/resources", response_model=SystemResourceStats)
async def get_system_resource_stats(
    _: AdminDetails = Depends(require_permission("system", "read")),
):
    """Fetch system resource stats without user metrics."""
    return await system_operator.get_system_resource_stats()


class UpdateCheckResponse(BaseModel):
    """Server-side GitHub release check.

    The dashboard must not query api.github.com itself — it is blocked for
    many users' browsers (e.g. Iran), which silently killed the update
    banner. The panel host reaches GitHub freely, so it checks for us.
    """

    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
    error: str | None = None


_UPDATE_CHECK_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
UPDATE_CHECK_OK_TTL = 1800.0
UPDATE_CHECK_ERR_TTL = 300.0
_UPDATE_REPO_API = "https://api.github.com/repos/behymin12345-hash/DR-VPN/releases/latest"


def _version_tuple(version: str) -> tuple[int, ...]:
    import re as _re

    parts = _re.findall(r"\d+", version)
    return tuple(int(p) for p in parts[:3])


@router.get("/system/update-check", response_model=UpdateCheckResponse)
async def system_update_check(
    _: AdminDetails = Depends(require_permission("system", "read")),
):
    """Compare this panel's version with the latest GitHub release (30 min cache)."""
    from app import __version__

    now = time.monotonic()
    cached = _UPDATE_CHECK_CACHE["data"]
    ttl = UPDATE_CHECK_OK_TTL if cached and cached.get("latest_version") else UPDATE_CHECK_ERR_TTL
    if cached is not None and now - _UPDATE_CHECK_CACHE["at"] < ttl:
        return UpdateCheckResponse(**cached)

    latest: str | None = None
    url: str | None = None
    error: str | None = None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(_UPDATE_REPO_API, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code == 200:
            data = resp.json()
            latest = (data.get("tag_name") or "").lstrip("v") or None
            url = data.get("html_url")
        else:
            error = f"github api status {resp.status_code}"
    except Exception as exc:
        error = f"{exc.__class__.__name__}"

    update_available = False
    if latest:
        try:
            update_available = _version_tuple(latest) > _version_tuple(__version__)
        except ValueError:
            update_available = False

    payload = {
        "current_version": __version__,
        "latest_version": latest,
        "update_available": update_available,
        "release_url": url,
        "error": error,
    }
    _UPDATE_CHECK_CACHE["data"] = payload
    _UPDATE_CHECK_CACHE["at"] = now
    return UpdateCheckResponse(**payload)


@router.get("/system/users", response_model=SystemUsersStats)
async def get_system_users_stats(
    admin_username: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("users", "read")),
):
    """Fetch user stats and traffic metrics without system resource stats."""
    return await system_operator.get_system_users_stats(db, admin=admin, admin_username=admin_username)


@router.get("/inbounds", response_model=list[str])
async def get_inbounds(_: AdminDetails = Depends(require_permission("system", "read"))):
    """Retrieve inbound configurations grouped by protocol."""
    return await system_operator.get_inbounds()


@router.get("/inbounds/details", response_model=list[InboundSummary])
async def get_inbound_details(_: AdminDetails = Depends(require_permission("system", "read"))):
    """Retrieve lightweight inbound metadata for dashboard forms."""
    return await system_operator.get_inbound_details()


@router.get("/wireguard/subnets", response_model=list[WireGuardSubnetUsage])
async def get_wireguard_subnets(
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("cores", "read")),
):
    """Per-subnet WireGuard address usage: capacity, used/free counts and the first free IPs."""
    return await get_subnet_usage(db)


async def _measure_worker_health(request_coro) -> WorkerHealth:
    start = time.monotonic()
    try:
        await request_coro
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return WorkerHealth(status="ok", response_time_ms=elapsed_ms)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        error_msg = str(exc) or exc.__class__.__name__
        return WorkerHealth(status="down", response_time_ms=elapsed_ms, error=error_msg)


@router.get("/workers/health", response_model=WorkersHealth)
async def get_workers_health(_: AdminDetails = Depends(require_permission("system", "read"))):
    if not is_nats_enabled():
        disabled = WorkerHealth(status="disabled")
        return WorkersHealth(scheduler=disabled, node=disabled)

    timeout = 5.0
    scheduler_task = _measure_worker_health(scheduler_nats_client.request("health_check", {}, timeout))
    node_task = _measure_worker_health(node_nats_client.request("health_check", {}, timeout))
    scheduler_health, node_health = await asyncio.gather(scheduler_task, node_task)

    return WorkersHealth(scheduler=scheduler_health, node=node_health)


@router.post(TELEGRAM_WEBHOOK_PATH, include_in_schema=False)
async def webhook_handler(request: Request, X_Telegram_Bot_Api_Secret_Token: str = Header()):
    """Telegram webhook handler"""
    settings: Telegram = await telegram_settings()

    if not settings.enable:
        raise HTTPException(status_code=404, detail="not found")

    if X_Telegram_Bot_Api_Secret_Token != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid secret key")

    bot = get_bot()
    if not bot:
        return JSONResponse(status_code=200, content={"status": "ok"})
    dp = get_dispatcher()

    # aiogram is imported on first webhook hit only; the bot-disabled panel
    # (the common small-VPS case) never pays the ~30MB aiogram import cost.
    from aiogram.types import Update

    update_data = await request.json()
    update = Update.model_validate(update_data, context={"bot": bot})
    asyncio.create_task(dp.feed_update(bot, update))
    return JSONResponse(status_code=200, content={"status": "ok"})
