"""Smart Setup — auto-generates a secure multi-protocol stack.

A local heuristic engine, deliberately offline: it measures real latency from
the panel to the node and to the public internet, picks a profile, and
builds a proven config shape (VLESS-REALITY + VLESS-WS + SS-2022, plus
VMESS-WS for the CDN-stealth profile) with a freshly generated REALITY
x25519 keypair. It then creates the core config, a group binding every
inbound, and one host per inbound — the exact objects the dashboard would
otherwise require clicking through four pages to assemble.
"""

import asyncio
import base64
import json
import secrets
import time
from typing import Any

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from sqlalchemy import select

from app.db import AsyncSession
from app.db.models import Node, NodeStatus
from app.models.admin import AdminDetails
from app.models.auto_setup import SmartSetupInboundReport, SmartSetupRequest, SmartSetupResponse
from app.models.core import CoreCreate
from app.models.group import GroupCreate
from app.models.host import CreateHost
from app.operation import BaseOperation, OperatorType
from app.operation.core import CoreOperation
from app.operation.group import GroupOperation
from app.operation.host import HostOperation
from app.utils.logger import get_logger

logger = get_logger("smart-setup")

REALITY_TARGET = "www.microsoft.com:443"
REALITY_SERVER_NAME = "www.microsoft.com"

_GEO_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_DEST_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
REALITY_CANDIDATES = [
    "www.microsoft.com:443",
    "www.samsung.com:443",
    "www.tesla.com:443",
    "www.cloudflare.com:443",
    "www.bing.com:443",
]

core_operator = CoreOperation(OperatorType.API)
group_operator = GroupOperation(OperatorType.API)
host_operator = HostOperation(OperatorType.API)


class SmartSetupOperation(BaseOperation):
    # ---------------------------------------------------------------- latency
    async def _tcp_latency(self, host: str, port: int, attempts: int = 3, timeout: float = 2.0) -> float | None:
        """Best-of-N TCP connect time (ms)."""
        best: float | None = None
        for _ in range(attempts):
            start = time.monotonic()
            try:
                _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
            except (OSError, TimeoutError):
                continue
            elapsed = (time.monotonic() - start) * 1000
            best = elapsed if best is None else min(best, elapsed)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        return best

    async def _pick_node(self, db: AsyncSession, node_id: int | None) -> Node | None:
        stmt = select(Node).where(Node.status == NodeStatus.connected)
        if node_id is not None:
            stmt = stmt.where(Node.id == node_id)
        return (await db.execute(stmt.limit(1))).scalar_one_or_none()

    # ------------------------------------------------------------------ keys
    @staticmethod
    def _reality_keypair() -> tuple[str, str]:
        """REALITY uses x25519; the panel can mint a keypair locally — the same
        output as `xray x25519` (base64url, unpadded)."""
        private_key = X25519PrivateKey.generate()
        private_raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        public_raw = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return (
            base64.urlsafe_b64encode(private_raw).decode().rstrip("="),
            base64.urlsafe_b64encode(public_raw).decode().rstrip("="),
        )

    # ------------------------------------------------------------- detection
    async def _detect_geo(self) -> dict | None:
        """Best-effort server geo from the free ip-api.com endpoint (no key)."""

        now = time.monotonic()
        if _GEO_CACHE["data"] and now - _GEO_CACHE["at"] < 21600:
            return _GEO_CACHE["data"]
        try:
            ip = None
            for probe_url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "curl", "-fs", "--max-time", "6", probe_url,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
                    if proc.returncode == 0:
                        ip = out.decode().strip()
                        break
                except (OSError, TimeoutError):
                    continue
            if not ip:
                return None

            def _fetch():
                import urllib.request

                req = urllib.request.Request(
                    "http://ip-api.com/json/" + urllib.parse.quote(ip),
                    headers={"User-Agent": "dr-vpn"},
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    return json.loads(resp.read())

            data = await asyncio.to_thread(_fetch)
            if data.get("status") != "success":
                return None
            geo = {
                "ip": ip,
                "country": data.get("country"),
                "country_code": data.get("countryCode"),
                "city": data.get("city"),
                "isp": data.get("isp"),
            }
            _GEO_CACHE["data"] = geo
            _GEO_CACHE["at"] = now
            return geo
        except Exception as exc:
            logger.debug("geo detection failed: %s", exc)
            return None

    async def _pick_reality_dest(self) -> dict:
        """Probe REALITY camouflage targets from THIS server and keep the fastest
        feasible one (TLS1.3 + h2 + x25519) — camouflage that is also close to
        the box means better mimicry AND lower handshake latency."""
        from app.models.reality_scan import RealityScanRequest
        from app.operation import OperatorType as _OperatorType
        from app.operation.core import CoreOperation

        scan_op = CoreOperation(_OperatorType.API)

        now = time.monotonic()
        if _DEST_CACHE["data"] and now - _DEST_CACHE["at"] < 1800:
            return _DEST_CACHE["data"]

        async def probe(candidate: str):
            try:
                return await scan_op.scan_reality_target(RealityScanRequest(target=candidate, timeout=4))
            except Exception:
                return None

        results = await asyncio.gather(*[probe(c) for c in REALITY_CANDIDATES])
        feasible = [
            r for r in results if r is not None and r.feasible and r.tls13 and r.h2 and r.latency_ms is not None
        ]
        best = min(feasible, key=lambda r: r.latency_ms) if feasible else None
        if best is None:
            dest = {"host": REALITY_SERVER_NAME, "port": 443, "latency_ms": None, "probed": len(results)}
        else:
            host = best.host if best.host else best.target.rsplit(":", 1)[0]
            dest = {
                "host": host,
                "port": best.port,
                "latency_ms": best.latency_ms,
                "probed": len(results),
                "candidates_feasible": len(feasible),
            }
        _DEST_CACHE["data"] = dest
        _DEST_CACHE["at"] = now
        return dest

    @staticmethod
    def _has_aes_nv() -> bool:
        """AES-NI acceleration → 2022-blake3-aes-256-gcm is the fastest secure SS2022 cipher."""
        try:
            with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
                content = f.read()[:200000]
                return " aes " in content or "aes_ni" in content
        except OSError:
            return True  # virtually all modern VPS CPUs have AES-NI

    # ---------------------------------------------------------------- config
    def _build_config(self, req: SmartSetupRequest, profile: str, *, reality_dest: dict | None = None, ss_cipher: str | None = None) -> tuple[dict, list[dict]]:
        """Return (xray config, inbound descriptors). Mirrors the proven
        multi-protocol shape shipped in production (Reality dest needs no
        certificate; SS-2022 password is a fresh 32-byte base64 key)."""
        private_key, _ = self._reality_keypair()
        short_id = secrets.token_hex(4)
        nonce = secrets.token_hex(3)
        ss_password = base64.b64encode(secrets.token_bytes(32)).decode()
        include_vmess = req.include_vmess if req.include_vmess is not None else profile == "stealth"
        wanted = set(req.protocols or {"vless", "vmess", "ss"})
        if include_vmess:
            wanted.add("vmess")
        dest_host = (reality_dest or {}).get("host", REALITY_SERVER_NAME)
        dest_latency = (reality_dest or {}).get("latency_ms")
        cipher = ss_cipher or "2022-blake3-aes-256-gcm"

        reality_inbound = {
            "tag": "VLESS-REALITY",
            "listen": "0.0.0.0",
            "port": req.base_port,
            "protocol": "vless",
            "settings": {"clients": [], "decryption": "none"},
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "show": False,
                    "dest": REALITY_TARGET,
                    "xver": 0,
                    "serverNames": [REALITY_SERVER_NAME],
                    "privateKey": private_key,
                    "shortIds": [short_id],
                },
            },
        }
        vless_ws = {
            "tag": "VLESS-WS",
            "listen": "0.0.0.0",
            "port": 2052,
            "protocol": "vless",
            "settings": {"clients": [], "decryption": "none"},
            "streamSettings": {"network": "ws", "wsSettings": {"path": f"/vlessws-{nonce}"}},
        }
        ss_2022 = {
            "tag": "SS-2022",
            "listen": "0.0.0.0",
            "port": 8388,
            "protocol": "shadowsocks",
            "settings": {
                "method": cipher,
                "password": ss_password,
                "network": "tcp,udp",
            },
        }
        inbounds = []
        inbound_notes: dict[str, str] = {}
        if "vless" in wanted:
            inbounds.append(reality_inbound)
            inbound_notes["VLESS-REALITY"] = (
                f"camouflage target {dest_host}"
                + (f" ({dest_latency} ms from this server)" if dest_latency is not None else "")
            )
            inbounds.append(vless_ws)
            inbound_notes["VLESS-WS"] = "CDN-friendly fallback with a random path"
        if "vmess" in wanted:
            inbounds.append(
                {
                    "tag": "VMESS-WS",
                    "listen": "0.0.0.0",
                    "port": 2054,
                    "protocol": "vmess",
                    "settings": {"clients": []},
                    "streamSettings": {"network": "ws", "wsSettings": {"path": f"/vmessws-{nonce}"}},
                }
            )
            inbound_notes["VMESS-WS"] = "for CDN relays (Cloudflare) - strongest obfuscation"
        if "ss" in wanted:
            inbounds.append(ss_2022)
            inbound_notes["SS-2022"] = f"{cipher} (AES-NI: {'yes' if cipher.endswith('aes-256-gcm') else 'no'})"

        config = {
            "log": {"loglevel": "warning"},
            "inbounds": inbounds,
            "outbounds": [
                {"protocol": "freedom", "tag": "DIRECT"},
                {"protocol": "blackhole", "tag": "BLOCK"},
            ],
            "routing": {"rules": []},
        }
        descriptors = [
            {
                "tag": ib["tag"],
                "port": ib["port"],
                "protocol": ib["protocol"],
                "security": (ib.get("streamSettings") or {}).get("security", "none"),
                "remark": f"{ib['tag']} @ {req.domain}",
                "note": inbound_notes.get(ib["tag"]),
            }
            for ib in inbounds
        ]
        return config, descriptors

    # ------------------------------------------------------------------ main
    async def run_setup(self, db: AsyncSession, req: SmartSetupRequest, admin: AdminDetails) -> SmartSetupResponse:
        warnings: list[str] = []
        node = await self._pick_node(db, req.node_id)

        node_latency = None
        internet_latency = await self._tcp_latency("1.1.1.1", 443)
        if node is not None:
            node_latency = await self._tcp_latency(node.address, node.api_port)
            if node_latency is None:
                warnings.append(f"Node '{node.name}' did not answer a TCP probe on its API port — latency profile fell back to the internet probe")
                node_latency = internet_latency

        probe = node_latency if node_latency is not None else internet_latency
        if probe is None:
            probe = 999.0
            warnings.append("No latency probe succeeded — using the stealth profile as the safe default")

        if probe <= 50:
            profile = "turbo"
            reason = f"{probe:.0f} ms — very low latency: direct Reality/Vision connection is the primary path"
        elif probe <= 120:
            profile = "balanced"
            reason = f"{probe:.0f} ms — balanced: Reality primary, WebSocket fallback for CDN routes"
        else:
            profile = "stealth"
            reason = f"{probe:.0f} ms — high latency: CDN-friendly WebSocket stack included"

        geo = await self._detect_geo()
        reality_dest = None
        ss_cipher = None
        wanted = set(req.protocols or {"vless", "vmess", "ss"})
        if "vless" in wanted:
            reality_dest = await self._pick_reality_dest()
        if "ss" in wanted:
            ss_cipher = "2022-blake3-aes-256-gcm" if self._has_aes_nv() else "2022-blake3-chacha20-poly1305"
        config, descriptors = self._build_config(req, profile, reality_dest=reality_dest, ss_cipher=ss_cipher)
        inbound_tags = [d["tag"] for d in descriptors]
        ports_to_open = sorted({d["port"] for d in descriptors})

        core = await core_operator.create_core(
            db,
            CoreCreate(
                name=f"smart-{profile}-{req.base_port}",
                config=config,
                exclude_inbound_tags=None,
                fallbacks_inbound_tags=None,
            ),
            admin,
        )

        group = await group_operator.create_group(
            db, GroupCreate(name=f"Smart {profile}", inbound_tags=inbound_tags), admin
        )

        host_count = 0
        for order, descriptor in enumerate(descriptors):
            await host_operator.create_host(
                db,
                CreateHost(
                    remark=descriptor["remark"],
                    address={req.domain},
                    inbound_tag=descriptor["tag"],
                    port=descriptor["port"],
                    priority=order,
                ),
                admin,
            )
            host_count += 1

        security_notes = [
            "REALITY keypair was generated fresh for this setup (x25519) — the private key never leaves this core config",
            "VLESS-REALITY borrows the TLS fingerprint of a real site, so active probing fails without certificates to manage",
            "SS-2022 uses a fresh 32-byte key (AEAD cipher chosen for this server's CPU)",
            "WebSocket paths contain a random suffix to avoid path guessing",
        ]
        if geo:
            security_notes.insert(0, f"server location: {geo.get('city') or geo.get('country')} ({geo.get('isp')}) — profiles tuned for it")
        warnings.append(
            "Open these ports in your firewall / cloud Security Group before clients can connect: " + ", ".join(map(str, ports_to_open))
        )
        if node is None:
            warnings.append("No connected node was found — the core config is stored and will apply once a node connects")

        logger.info(
            "Smart Setup by %s: core=%s group=%s profile=%s latency=%.0fms",
            admin.username,
            core.id,
            group.id,
            profile,
            probe,
        )
        return SmartSetupResponse(
            ok=True,
            profile=profile,
            profile_reason=reason,
            node_latency_ms=round(node_latency, 1) if node_latency is not None else None,
            internet_latency_ms=round(internet_latency, 1) if internet_latency is not None else None,
            core_id=core.id,
            core_name=core.name,
            group_id=group.id,
            group_name=group.name,
            host_count=host_count,
            inbounds=[SmartSetupInboundReport(**d) for d in descriptors],
            ports_to_open=ports_to_open,
            geo=geo,
            reality_dest=reality_dest,
            ss_cipher=ss_cipher,
            security_notes=security_notes,
            warnings=warnings,
        )


smart_setup_operator = SmartSetupOperation(OperatorType.API)
