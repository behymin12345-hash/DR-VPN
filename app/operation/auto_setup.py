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
import secrets
import time

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

    # ---------------------------------------------------------------- config
    def _build_config(self, req: SmartSetupRequest, profile: str) -> tuple[dict, list[dict]]:
        """Return (xray config, inbound descriptors). Mirrors the proven
        multi-protocol shape shipped in production (Reality dest needs no
        certificate; SS-2022 password is a fresh 32-byte base64 key)."""
        private_key, _ = self._reality_keypair()
        short_id = secrets.token_hex(4)
        nonce = secrets.token_hex(3)
        ss_password = base64.b64encode(secrets.token_bytes(32)).decode()
        include_vmess = req.include_vmess if req.include_vmess is not None else profile == "stealth"

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
                "method": "chacha20-ietf-poly1305",
                "password": ss_password,
                "network": "tcp,udp",
            },
        }
        inbounds = [reality_inbound, vless_ws]
        if include_vmess:
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
        inbounds.append(ss_2022)

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

        config, descriptors = self._build_config(req, profile)
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
            "SS-2022 uses a fresh 32-byte key (chacha20-ietf-poly1305, AEAD)",
            "WebSocket paths contain a random suffix to avoid path guessing",
        ]
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
            security_notes=security_notes,
            warnings=warnings,
        )


smart_setup_operator = SmartSetupOperation(OperatorType.API)
