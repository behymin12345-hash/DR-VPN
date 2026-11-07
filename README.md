<p align="center">
  <a href="#" target="_blank" rel="noopener noreferrer">
    <img width="160" height="160" src="assets/branding/logo.png" alt="DR-VPN logo">
  </a>
</p>

<h1 align="center">⚡ DR-VPN</h1>

<p align="center">
    <strong>Lightweight Proxy Management Panel</strong>
</p>

<p align="center">
  <a href="./README-fa.md">🇮🇷 فارسی</a>
</p>

---

> [!WARNING]
> **DR-VPN is an early release (v0.1.0) under active development.** It is functional
> software (the test suite passes and the panel boots), but the dedicated installer,
> the reseller module and the performance benchmark reports are still on the roadmap.
> See the [Roadmap](#️-roadmap) for what is done and what is not.

## 📖 What is DR-VPN?

DR-VPN is a lightweight, self-hosted proxy management panel for running and
administering hundreds of proxy accounts through a clean web dashboard, a full
REST API and a CLI. It manages [Xray-core](https://github.com/XTLS/Xray-core)
configurations and works with remote Xray nodes.

DR-VPN is a fork of
[PasarGuard](https://github.com/PasarGuard/panel) (AGPL-3.0), which is itself
derived from [Marzban](https://github.com/Gozargah/Marzban). DR-VPN's goals are
a fully independent visual identity, a reseller ("sponsorship") system,
first-class Persian/English UX, and reduced resource usage on small VPS
servers. All credit for the underlying codebase belongs to the upstream
projects — see [NOTICE.md](NOTICE.md).

## ✨ Features

**🌐 Web Interface & API**
- Built-in **Web UI** dashboard (React) with dark/light themes
- Fully **REST API** backend (OpenAPI schema included)
- **Multi-Node** support for infrastructure distribution

**🔐 Protocols & Security**
- Supports **Vmess**, **VLESS**, **Trojan**, **Shadowsocks**, **WireGuard** and **Hysteria2**
- **TLS** and **REALITY** support
- **Multi-protocol** for a single user

**👥 User Management**
- **Multi-user** on a single inbound, **multi-inbound** on a single port (fallbacks)
- **Traffic** and **expiry** limits, periodic limits (daily, weekly, …)
- **HWID/device** limits
- **Multi-admin** with **RBAC** (scoped permissions, per-admin user ownership)

**🔗 Subscriptions & Sharing**
- Subscription links compatible with **V2ray**, **Clash**, **ClashMeta**, **sing-box** and more
- Automatic **share link** and **QR code** generation
- Traffic statistics and monitoring

**🛠️ Tools & Customization**
- Customizable Xray configuration with validation
- Integrated **Telegram Bot** (optional)
- **CLI** for setup keys and administration
- **Multi-language** UI (English / فارسی / Русский / 中文) with full RTL support

## 🚀 Installation (manual, v0.1.0)

> A one-command installer script is on the roadmap. For now, install manually.

Requirements: Linux x86_64 (Ubuntu 20.04/22.04/24.04 recommended) or Windows for
development, plus [uv](https://docs.astral.sh/uv/).

```bash
# 1. Get the code
git clone https://github.com/behymin12345-hash/DR-VPN.git
cd DR-VPN

# 2. Install Python 3.14 + dependencies (uv manages everything)
uv sync

# 3. Configure
cp .env.example .env   # then edit UVICORN_UVicorn settings as needed

# 4. Run the panel
uv run python main.py

# 5. In another terminal, create a one-time setup key for the owner account
uv run python drvpn-cli.py generate-temp-key
```

Then open the dashboard and use the setup key to create the owner account.
Without SSL certificates the panel binds to localhost only — use an SSL
certificate or SSH port forwarding for first access:

```bash
ssh -L 8000:localhost:8000 user@serverip
# then open http://localhost:8000/dashboard/
```

See [INSTALL.md](INSTALL.md) for details, environment variables and systemd notes.

### Docker

```bash
docker build -t dr-vpn .
docker run -d --name dr-vpn --network host -v /var/lib/drvpn:/var/lib/drvpn --env-file .env dr-vpn
```

## 📚 Documentation

- Full documentation (upstream, matches current functionality): [docs.pasarguard.org](https://docs.pasarguard.org)
- Architecture analysis of this fork: [docs/ARCHITECTURE-REPORT.md](docs/ARCHITECTURE-REPORT.md)

## 🗺️ Roadmap

| Stage | Scope | Status |
|---|---|---|
| 1 | Repository architecture analysis | ✅ Done |
| 2 | DR-VPN branding & identity | ✅ Done |
| 3 | Performance pass, resource profiles, benchmarks | 🔨 In progress (test suite green baseline first) |
| 4 | Core functionality hardening | ⏳ Planned |
| 5 | Sponsorship / **reseller** module | ⏳ Planned |
| 6 | Full dashboard redesign + fa/en default | ⏳ Planned |
| 7 | Linux installer (install/update/backup scripts, systemd) | ⏳ Planned |
| 8 | Security & QA pass | ⏳ Planned |
| 9 | Mature public release | ⏳ Planned |

## 📄 License & Attribution

DR-VPN is licensed under the **[GNU AGPL-3.0](LICENSE)**, inherited from
PasarGuard. The upstream projects retain full credit for the original codebase:

- [PasarGuard](https://github.com/PasarGuard/panel) — AGPL-3.0, © PasarGuard organization
- [Marzban](https://github.com/Gozargah/Marzban) — the original Marzban project

If you run a modified version of this software as a network service, AGPL-3.0
§13 requires you to offer its Corresponding Source to your service's users.
See [NOTICE.md](NOTICE.md) for details.

---

<p align="center">
  DR-VPN · an independent identity for a proven codebase
</p>
