"""Cloudflare WARP as a DR-VPN location provider.

WARP is a plain WireGuard tunnel to Cloudflare — registered once through the
official client API (no account needed, "Anonymous" device), then used as an
xray *wireguard* outbound so any inbound can route its traffic out through
Cloudflare instead of the server IP. Unlike tor-ml there is no country pin:
the exit is Cloudflare's anycast edge, which is exactly what unblocks
Telegram-heavy setups and adds a fast, low-latency hop to the mix.
"""

import base64
import json
import secrets
import time
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

logger = get_logger("warp")

WARP_STATE_PATH = Path("/var/lib/dr-vpn/warp.json")
WARP_API = "https://api.cloudflareclient.com/v0a2158/reg"
WARP_PEER_FALLBACK_PUBKEY = "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="
WARP_ENDPOINT_HOST = "engage.cloudflareclient.com"
WARP_ENDPOINT_PORT = 2408


def _warp_http_register(public_key: str) -> dict[str, Any]:
    """Register an Anonymous WARP device and return the raw response config."""
    import urllib.error
    import urllib.request

    body = {
        "install_id": "",
        "fcm_token": "",
        "tos": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "model": "PC",
        "serial_number": secrets.token_hex(16),
        "locale": "en_US",
        "key": public_key,
        "warp_enabled": True,
        "type": "Anonymous",
    }
    req = urllib.request.Request(
        WARP_API,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "okhttp/3.12.1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def load_warp_state() -> dict[str, Any] | None:
    try:
        return json.loads(WARP_STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def build_warp_outbound(state: dict[str, Any], tag: str = "warp") -> dict[str, Any]:
    """The xray *wireguard* outbound for the registered WARP device."""
    return {
        "tag": tag,
        "protocol": "wireguard",
        "settings": {
            "secretKey": state["secret_key"],
            "address": [state.get("address", "172.16.0.2/32")],
            "peers": [
                {
                    "publicKey": state["peer_key"],
                    "allowedIPs": ["0.0.0.0/0"],
                    "endpoint": f"{state.get('endpoint_host', WARP_ENDPOINT_HOST)}:{state.get('endpoint_port', WARP_ENDPOINT_PORT)}",
                    "reserved": state["reserved"],
                }
            ],
            "mtu": 1280,
        },
    }


async def register_warp() -> dict[str, Any]:
    """Register a WARP device (or reuse the existing one) and persist it.

    Returns the saved state dict including everything needed to build the
    xray wireguard outbound.
    """
    existing = load_warp_state()
    if existing:
        return existing

    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    key = X25519PrivateKey.generate()
    secret_key = base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode()
    public_key = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()

    import asyncio

    data = await asyncio.to_thread(_warp_http_register, public_key)
    config = data.get("config", {})
    interface = config.get("interface", {})
    peers = config.get("peers") or [{}]
    peer = peers[0]
    client_id = config.get("client_id", "")
    reserved = list(base64.b64decode(client_id + "=" * (-len(client_id) % 4))) if client_id else []

    endpoint_v4 = ((peer.get("endpoint") or {}).get("v4")) or ""
    endpoint_ip = endpoint_v4.rsplit(":", 1)[0] if endpoint_v4 else WARP_ENDPOINT_HOST
    address_v4 = (interface.get("addresses") or {}).get("v4") or "172.16.0.2"

    state: dict[str, Any] = {
        "device_id": data.get("id"),
        "secret_key": secret_key,
        "address": f"{address_v4}/32",
        "peer_key": peer.get("public_key") or WARP_PEER_FALLBACK_PUBKEY,
        "endpoint_host": WARP_ENDPOINT_HOST,
        "endpoint_port": WARP_ENDPOINT_PORT,
        "endpoint_ip": endpoint_ip,
        "reserved": reserved,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    WARP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    WARP_STATE_PATH.write_text(json.dumps(state, indent=2))
    WARP_STATE_PATH.chmod(0o600)
    logger.info("WARP device registered (id=%s reserved=%s)", state["device_id"], reserved)
    return state


def remove_warp_state() -> bool:
    try:
        WARP_STATE_PATH.unlink()
        return True
    except OSError:
        return False
