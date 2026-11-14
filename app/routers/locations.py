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

# DR-VPN RAM/ping tune for tor-ml (applied to the installed CLI, idempotent):
# 1. drop per-destination SOCKS isolation so circuits are shared — fewer
#    circuits, less RAM, warm/fast repeat connections (the exit is pinned per
#    location anyway, so destination isolation buys nothing here);
# 2. "weak" preset becomes the RAM-saver preset: 8 MB queue cap (was 16),
#    30-minute circuit lifetime (was 15) so pings and connections stay warm.
# All sed targets are unique strings inside tor-ml v4.4.
TUNE_CMD = (
    "bash -c 'cp -f /usr/local/bin/tor /usr/local/bin/tor.bak 2>/dev/null || true; "
    "sed -i \"s/ IsolateDestAddr IsolateDestPort//\" /usr/local/bin/tor; "
    "sed -i \"s/^MaxMemInQueues 16 MB$/MaxMemInQueues 8 MB/; "
    "s/^NewCircuitPeriod 90$/NewCircuitPeriod 150/; "
    "s/^MaxCircuitDirtiness 900$/MaxCircuitDirtiness 1800/\" /usr/local/bin/tor; "
    "bash -n /usr/local/bin/tor'"
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


async def apply_ram_tune() -> tuple[bool, str]:
    """Apply the DR-VPN RAM/ping tune to the installed tor-ml CLI.

    Idempotent sed patch (safe to run on every install/status call); keeps a
    one-time .bak backup and syntax-checks the result.
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            TUNE_CMD,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        ok = proc.returncode == 0 and "syntax error" not in out.decode(errors="replace").lower()
        return ok, out.decode(errors="replace")[:300]
    except (TimeoutError, OSError) as exc:
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
    """Install tor-ml on this server (the panel server itself). Long-running.

    Always re-applies the DR-VPN RAM/ping tune afterwards — including on an
    already-installed CLI, so clicking Install again on an old install also
    upgrades it.
    """
    ok, out = await _run_tor(["--json-status"], timeout=20)
    if ok:
        tuned, tune_out = await apply_ram_tune()
        return {
            "ok": True,
            "message": "tor-ml is already installed" + (" — RAM/ping tune applied" if tuned else ""),
            "tuned": tuned,
            "tune_output": tune_out,
            "status": {"installed": True},
        }

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
    tuned, tune_out = await apply_ram_tune()
    ok, _ = await _run_tor(["--json-status"], timeout=20)
    if not ok:
        raise HTTPExceptionServiceUnavailable(f"install finished but the CLI is not responding: {tail}")
    return {"ok": True, "message": "tor-ml installed", "tuned": tuned, "tune_output": tune_out, "log_tail": tail}


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


# ---------------------------------------------------------------------------
# Cloudflare WARP — a location provider that is not tor-ml: a WireGuard
# tunnel to Cloudflare's anycast edge. Fast, no country pin, ideal as an
# unblocking hop next to Tor/Psiphon.
# ---------------------------------------------------------------------------


class WarpOutboundResponse(BaseModel):
    registered: bool
    device_id: str | None = None
    outbound: dict | None = None
    warnings: list[str] = Field(default_factory=list)


@router.get("/warp", response_model=WarpOutboundResponse)
async def get_warp(
    _: AdminDetails = Depends(require_permission("settings", "read")),
):
    from app.operation.warp import build_warp_outbound, load_warp_state

    state = load_warp_state()
    if not state:
        return WarpOutboundResponse(registered=False)
    return WarpOutboundResponse(
        registered=True,
        device_id=state.get("device_id"),
        outbound=build_warp_outbound(state),
        warnings=["Open UDP 2408 outbound on your firewall/Security Group for the WARP tunnel."],
    )


@router.post("/warp", response_model=WarpOutboundResponse)
async def register_warp_device(
    _: AdminDetails = Depends(require_permission("settings", "update")),
):
    """Register a Cloudflare WARP device (idempotent) and return its wireguard outbound."""
    from app.operation.warp import build_warp_outbound, register_warp

    try:
        state = await register_warp()
    except Exception as exc:
        logger.error(f"WARP registration failed: {exc}")
        raise HTTPExceptionServiceUnavailable(f"WARP registration failed: {exc}")
    return WarpOutboundResponse(
        registered=True,
        device_id=state.get("device_id"),
        outbound=build_warp_outbound(state),
        warnings=["Open UDP 2408 outbound on your firewall/Security Group for the WARP tunnel."],
    )


@router.delete("/warp")
async def remove_warp_device(
    _: AdminDetails = Depends(require_permission("settings", "update")),
):
    """Forget the local WARP registration (the device stays on Cloudflare's side)."""
    from app.operation.warp import remove_warp_state

    removed = remove_warp_state()
    return {"ok": True, "removed": removed}
