"""Panel-managed tor-ml locations (Telegram/exit locations via local SOCKS).

The panel and tor-ml run on the same box, so the backend can safely shell out
to the tor-ml CLI. Every argument is strictly validated; nothing user-supplied
reaches a shell string.
"""

import asyncio
import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.models.admin import AdminDetails
from app.utils.logger import get_logger

from .authentication import require_permission

router = APIRouter(tags=["Locations"], prefix="/api/locations")
logger = get_logger("locations")

TOR_CLI = "/usr/local/bin/tor"
INSTALLER_URL = "https://raw.githubusercontent.com/mrmarzx/Tor-ML-PRO/4.4/tor-ml.sh"
ID_PATTERN = re.compile(r"^[TP]\d{2}$")
MODE_PATTERN = re.compile(r"^(weak|normal|max)$")

INSTALL_CMD = (
    "bash -c 'curl -fsSL "
    + INSTALLER_URL
    + " | tr -d \"\\r\" > /root/tor-ml.sh && chmod +x /root/tor-ml.sh && /root/tor-ml.sh --install'"
)


class LocationIdsRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=88)

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, value: list[str]) -> list[str]:
        for item in value:
            if not ID_PATTERN.fullmatch(item):
                raise ValueError("location ids must look like T01 or P05")
        return list(dict.fromkeys(value))


class LocationModeRequest(BaseModel):
    mode: str

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if not MODE_PATTERN.fullmatch(value):
            raise ValueError("mode must be weak, normal or max")
        return value


async def _run_tor(args: list[str], timeout: float = 30) -> tuple[bool, str]:
    """Run the tor-ml CLI with the given arguments; never uses a shell."""
    try:
        proc = await asyncio.create_subprocess_exec(
            TOR_CLI,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode == 0, out.decode(errors="replace")
    except (TimeoutError, FileNotFoundError) as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


async def _fetch_status() -> dict:
    ok, out = await _run_tor(["--json-status"], timeout=20)
    if not ok:
        return {"installed": False, "ok": False, "running_count": 0, "locations": [], "raw": out[:300]}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"installed": False, "ok": False, "running_count": 0, "locations": [], "raw": out[:300]}
    return {"installed": True, **data}


@router.get("/status")
async def locations_status(
    _: AdminDetails = Depends(require_permission("settings", "read")),
):
    """Live tor-ml status: installed, mode, per-location running state."""
    ok, out = await _run_tor(["--json-status"], timeout=20)
    if not ok:
        return {"installed": False, "ok": False, "running_count": 0, "locations": [], "output": out[:300]}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"installed": False, "ok": False, "running_count": 0, "locations": [], "output": out[:300]}
    return {"installed": True, **data}


@router.post("/install")
async def install_tor_ml(
    _: AdminDetails = Depends(require_permission("settings", "update")),
):
    """Install tor-ml on this server (the panel server itself). Long-running."""
    ok, out = await _run_tor(["--json-status"], timeout=20)
    if ok:
        return {"ok": True, "message": "tor-ml is already installed", "status": {"installed": True}}

    proc = await asyncio.create_subprocess_shell(
        INSTALL_CMD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
    except TimeoutError:
        proc.kill()
        await self_report_failure("install timed out after 600s")
        raise HTTPExceptionServiceUnavailable("tor-ml install timed out")
    tail = out.decode(errors="replace")[-600:]
    if proc.returncode != 0:
        raise HTTPExceptionServiceUnavailable(f"tor-ml install failed: {tail}")
    ok, _ = await _run_tor(["--json-status"], timeout=20)
    if not ok:
        raise HTTPExceptionServiceUnavailable(f"install finished but the CLI is not responding: {tail}")
    return {"ok": True, "message": "tor-ml installed", "log_tail": tail}


def HTTPExceptionServiceUnavailable(detail: str):
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


async def self_report_failure(detail: str):
    logger.error(detail)


@router.post("/start")
async def start_locations(
    body: LocationIdsRequest,
    _: AdminDetails = Depends(require_permission("settings", "update")),
):
    for loc_id in body.ids:
        _ok, _ = await _run_tor(["--start", loc_id], timeout=60)
    return {"ok": True, "started": body.ids}


@router.post("/stop")
async def stop_locations(
    body: LocationIdsRequest,
    _: AdminDetails = Depends(require_permission("settings", "update")),
):
    for loc_id in body.ids:
        _ok, _ = await _run_tor(["--stop", loc_id], timeout=30)
    return {"ok": True, "stopped": body.ids}


@router.get("/ping/{loc_id}")
async def ping_location(
    loc_id: str,
    _: AdminDetails = Depends(require_permission("settings", "read")),
):
    if not ID_PATTERN.fullmatch(loc_id):
        return {"ok": False, "error": "invalid location id"}
    _ok, out = await _run_tor(["--ping", loc_id], timeout=45)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"id": loc_id, "ok": _ok, "raw": out[:200]}


@router.post("/mode")
async def set_mode(
    body: LocationModeRequest,
    _: AdminDetails = Depends(require_permission("settings", "update")),
):
    ok, out = await _run_tor(["--mode", body.mode], timeout=20)
    return {"ok": ok, "mode": body.mode, "output": out[:200]}
