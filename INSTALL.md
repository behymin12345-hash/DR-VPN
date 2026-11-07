# INSTALL — DR-VPN (v0.1.0)

Manual installation guide. A one-command Linux installer is planned (roadmap stage 7)
and is **not** implemented yet — this document describes the manual path.

## Requirements

| | |
|---|---|
| OS | Linux x86_64 — Ubuntu 20.04 / 22.04 / 24.04 recommended (any OS with Python works for development) |
| Python | **3.14** (installed automatically by [uv](https://docs.astral.sh/uv/)) |
| RAM | Works on small VPS; the 256/512 MB optimization profiles are being measured (no published numbers yet) |
| Database | SQLite (default, zero-config) · PostgreSQL · MySQL (optional) |

## 1. Get the code

```bash
git clone https://github.com/<OWNER>/DR-VPN.git
cd DR-VPN
```

## 2. Install uv and dependencies

```bash
# Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

uv sync          # downloads Python 3.14 if missing, creates .venv, installs deps
```

## 3. Configure

```bash
cp .env.example .env
```

Key variables (full annotated list in `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `UVICORN_HOST` | `0.0.0.0` | Without SSL certs the server refuses public binding and falls back to localhost |
| `UVICORN_PORT` | `8000` | |
| `UVICORN_SSL_CERTFILE` / `UVICORN_SSL_KEYFILE` | unset | Set both to enable HTTPS and public binding |
| `SQLALCHEMY_DATABASE_URL` | `sqlite+aiosqlite:///db.sqlite3` | SQLite by default; PostgreSQL/MySQL URLs supported |
| `UVICORN_WORKERS` | `1` | Values > 1 require `NATS_ENABLED=1` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Admin session lifetime |

## 4. Run

```bash
uv run python main.py
```

The panel serves:

- Dashboard: `http://localhost:8000/dashboard/`
- API: `http://localhost:8000/api/…`
- Health check: `http://localhost:8000/health`
- Subscription pages: `http://<host>/sub/<token>`

Without TLS, the panel binds to `localhost` only (a deliberate security default).
For first-time access on a headless server use SSH port forwarding:

```bash
ssh -L 8000:localhost:8000 user@serverip
# open http://localhost:8000/dashboard/
```

## 5. Create the owner account

```bash
uv run python drvpn-cli.py generate-temp-key
```

Use the printed one-time key on the dashboard's setup page to create the owner
(admin) account, then log in.

## 6. Run as a systemd service (manual unit)

Until the dedicated installer ships, you can create a minimal unit yourself:

```ini
# /etc/systemd/system/drvpn.service
[Unit]
Description=DR-VPN panel
After=network.target

[Service]
WorkingDirectory=/opt/DR-VPN
ExecStart=/opt/DR-VPN/.venv/bin/python main.py
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now drvpn
journalctl -u drvpn -f        # logs
```

Migrations run automatically? No — run them once after updates:

```bash
uv run alembic upgrade head
```

## 7. Docker (optional)

```bash
docker build -t dr-vpn .
docker run -d --name dr-vpn --network host \
  -v /var/lib/drvpn:/var/lib/drvpn \
  --env-file .env dr-vpn
```

## Backups

SQLite mode: stop the service and copy `db.sqlite3` (plus `.env` and
`/var/lib/pasarguard`-style data directories you configured). Backup/restore
scripts are part of roadmap stage 7.

## Support

- Upstream documentation (matches current functionality): <https://docs.pasarguard.org>
- Open an issue in this repository for DR-VPN-specific problems.
