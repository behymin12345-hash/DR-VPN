"""User-imported WireGuard tunnels as locations.

One step beyond the built-in WARP provider: the admin pastes any standard
wg-quick config (Mullvad, ProtonVPN, Windscribe, their own VPS …) and it
becomes an xray *wireguard* outbound — i.e. a country-exit location whose
IP belongs to the provider's server in that country.

Storage: /var/lib/dr-vpn/wg-tunnels/<slug>.json
"""

import json
import re
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

logger = get_logger("wg-tunnels")

WG_TUNNELS_DIR = Path("/var/lib/dr-vpn/wg-tunnels")
_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "tunnel"


def _parse_wg_quick(text: str) -> dict[str, Any]:
    """Parse the essentials out of a wg-quick config (interface + first peer)."""
    lowered = text.lower()
    if "[interface]" not in lowered or "[peer]" not in lowered:
        raise ValueError("config must contain [Interface] and [Peer] sections")
    iface: dict[str, str] = {}
    peer: dict[str, str] = {}
    section = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("[interface]"):
            section = iface
            continue
        if line.lower().startswith("[peer]"):
            section = peer
            continue
        if section is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        section[key.strip().lower()] = value.strip()

    private_key = iface.get("privatekey")
    if not private_key:
        raise ValueError("missing PrivateKey in [Interface]")
    peer_key = peer.get("publickey")
    if not peer_key:
        raise ValueError("missing PublicKey in [Peer]")
    endpoint = peer.get("endpoint")
    if not endpoint:
        raise ValueError("missing Endpoint in [Peer]")

    address = [a.strip() for a in re.split(r"[,\s]+", iface.get("address", "172.16.0.2/32")) if a.strip()]
    reserved: list[int] = []
    if "reserved" in peer:  # DR-VPN extension (WARP-style configs)
        try:
            reserved = [int(x) for x in re.findall(r"\d+", peer["reserved"])][:3]
        except ValueError:
            reserved = []

    return {
        "secret_key": private_key,
        "address": address,
        "peer_key": peer_key,
        "preshared_key": peer.get("presharedkey"),
        "endpoint": endpoint,
        "reserved": reserved,
        "listen_port": int(iface["listenport"]) if iface.get("listenport", "").isdigit() else None,
        "mtu": int(iface["mtu"]) if iface.get("mtu", "").isdigit() else 1280,
    }


def build_wg_outbound(tunnel: dict[str, Any], tag: str) -> dict[str, Any]:
    """The xray *wireguard* outbound for an imported tunnel."""
    peer: dict[str, Any] = {
        "publicKey": tunnel["peer_key"],
        "allowedIPs": ["0.0.0.0/0"],
        "endpoint": tunnel["endpoint"],
    }
    if tunnel.get("preshared_key"):
        peer["presharedKey"] = tunnel["preshared_key"]
    if tunnel.get("reserved"):
        peer["reserved"] = tunnel["reserved"]
    settings: dict[str, Any] = {
        "secretKey": tunnel["secret_key"],
        "address": tunnel["address"],
        "peers": [peer],
        "mtu": tunnel.get("mtu", 1280),
    }
    if tunnel.get("listen_port"):
        settings["listenPort"] = tunnel["listen_port"]
    return {"tag": tag, "protocol": "wireguard", "settings": settings}


def save_tunnel(name: str, config_text: str) -> dict[str, Any]:
    slug = slugify(name)
    parsed = _parse_wg_quick(config_text)
    tunnel = {"name": name.strip(), "slug": slug, **parsed}
    WG_TUNNELS_DIR.mkdir(parents=True, exist_ok=True)
    path = WG_TUNNELS_DIR / f"{slug}.json"
    path.write_text(json.dumps(tunnel, indent=2))
    path.chmod(0o600)
    logger.info("WireGuard tunnel imported: %s (%s endpoint)", slug, tunnel["endpoint"])
    return tunnel


def list_tunnels() -> list[dict[str, Any]]:
    if not WG_TUNNELS_DIR.exists():
        return []
    tunnels = []
    for path in sorted(WG_TUNNELS_DIR.glob("*.json")):
        try:
            tunnels.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return tunnels


def get_tunnel(slug: str) -> dict[str, Any] | None:
    try:
        return json.loads((WG_TUNNELS_DIR / f"{slug}.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def remove_tunnel(slug: str) -> bool:
    try:
        (WG_TUNNELS_DIR / f"{slug}.json").unlink()
        return True
    except OSError:
        return False


async def ping_tunnel(slug: str) -> dict[str, Any]:
    """ICMP latency to the tunnel endpoint's host (best of 3). WireGuard
    endpoints are UDP-only, so a TCP probe is meaningless — we measure the
    network path to the endpoint server instead, which is what dominates the
    tunnel's latency."""
    import asyncio

    tunnel = get_tunnel(slug)
    if not tunnel:
        return {"ok": False, "error": "tunnel not found"}
    endpoint = tunnel["endpoint"]
    host, _, _port = endpoint.rpartition(":")
    host = host.strip("[]")
    if not host:
        return {"ok": False, "error": f"bad endpoint: {endpoint}"}

    def run_ping() -> tuple[bool, str]:
        import subprocess

        try:
            out = subprocess.run(
                ["ping", "-c", "3", "-W", "2", host],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            ).stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"{exc.__class__.__name__}"
        m = re.search(r"=\s*[\d.]+/([\d.]+)/", out)
        if m:
            return True, m.group(1)
        if "100% packet loss" in out or "unreachable" in out:
            return False, "endpoint host does not answer ICMP (many VPN endpoints don't) - tunnel may still work"
        return False, "no rtt line"

    ok, value = await asyncio.to_thread(run_ping)
    if ok:
        return {"ok": True, "latency": float(value), "endpoint": host}
    return {"ok": False, "error": value, "endpoint": host}


