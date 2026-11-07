#!/usr/bin/env bash
# ============================================================================
#  DR-VPN installer / manager  —  https://github.com/behymin12345-hash/DR-VPN
#
#  One-command install (PasarGuard-style, native systemd — no Docker needed):
#    sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/behymin12345-hash/DR-VPN/main/scripts/drvpn.sh)" @ install
#
#  Commands: install update uninstall status logs restart stop start backup
#            restore cli edit-env version help
# ============================================================================

set -euo pipefail

# ----------------------------- defaults -------------------------------------
APP_DIR="/opt/dr-vpn"
APP_NAME="drvpn"
SERVICE_NAME="drvpn"
REPO_URL="https://github.com/behymin12345-hash/DR-VPN"
RAW_URL="https://raw.githubusercontent.com/behymin12345-hash/DR-VPN/main/scripts/drvpn.sh"
DATA_DIR="/var/lib/dr-vpn"
BACKUP_DIR="/var/backups/dr-vpn"
DB_FILE_NAME="db.sqlite3"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

msg()  { echo -e "${GREEN}[DR-VPN]${NC} $*"; }
warn() { echo -e "${YELLOW}[DR-VPN]${NC} $*"; }
err()  { echo -e "${RED}[DR-VPN]${NC} $*" >&2; }

# ----------------------------- helpers --------------------------------------

require_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This command must be run as root (use sudo)."
        exit 1
    fi
}

detect_os() {
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        OS_ID="${ID:-unknown}"
        OS_VER="${VERSION_ID:-unknown}"
    else
        OS_ID="unknown"; OS_VER="unknown"
    fi
    if [[ "$OS_ID" == "ubuntu" && "$OS_VER" =~ ^(20\.04|22\.04|24\.04)$ ]]; then
        msg "Detected supported OS: Ubuntu $OS_VER"
    else
        warn "Unsupported OS detected: ${OS_ID} ${OS_VER} (tested on Ubuntu 20.04/22.04/24.04). Continuing anyway…"
    fi
}

apt_install() {
    if command -v apt-get >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq "$@"
    else
        warn "apt-get not found; make sure the following are installed manually: $*"
    fi
}

is_port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -tln 2>/dev/null | awk '{print $4}' | grep -qE ":${port}$"
    else
        return 1
    fi
}

rand_password() {  # 20-char alphanumeric
    tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20
}

service_exists() { systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICE_NAME}\.service"; }

service_running() { systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; }

panel_version() {
    if [[ -f "$APP_DIR/app/version.py" ]]; then
        grep -oE '"?[0-9]+\.[0-9]+\.[0-9]+"?' "$APP_DIR/app/version.py" | tr -d '"' | head -1
    else
        echo "unknown"
    fi
}

run_as_panel() {  # run a command inside the app venv
    (cd "$APP_DIR" && uv run "$@")
}

# ----------------------------- install --------------------------------------

install_command() {
    require_root
    detect_os

    local db="sqlite" db_url="" ssl_domain="" port="8000" version="main" no_confirm="false"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --database) db="$2"; shift 2 ;;
            --db-url)   db_url="$2"; shift 2 ;;
            --port)     port="$2"; shift 2 ;;
            --ssl-domain) ssl_domain="$2"; shift 2 ;;
            --version)  version="v${2#v}"; shift 2 ;;
            --yes|-y)   no_confirm="true"; shift ;;
            *) err "Unknown install option: $1"; exit 1 ;;
        esac
    done

    if service_exists; then
        if [[ "$no_confirm" == "true" ]]; then
            err "DR-VPN is already installed. Re-run with 'uninstall' first."
            exit 1
        fi
        read -rp "DR-VPN is already installed. Reinstall and overwrite /opt/dr-vpn? [y/N]: " reply
        [[ "$reply" =~ ^[Yy]$ ]] || { warn "Aborted."; exit 0; }
        systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    fi

    # --- dependencies
    msg "Installing base dependencies…"
    apt_install curl git ca-certificates cron >/dev/null 2>&1 || true

    if ! command -v uv >/dev/null 2>&1; then
        msg "Installing uv (Python toolchain manager)…"
        curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh >/dev/null
    fi

    # --- port check
    if is_port_in_use "$port"; then
        read -rp "Port ${port} is already in use. Enter another port: " port
        if is_port_in_use "$port"; then
            err "Port ${port} is also in use. Aborting."
            exit 1
        fi
    fi

    # --- fetch source
    if [[ -d "$APP_DIR/.git" ]]; then
        msg "Updating existing source at $APP_DIR…"
        git -C "$APP_DIR" fetch --tags --force >/dev/null 2>&1 || true
        git -C "$APP_DIR" checkout "$version" >/dev/null 2>&1 || git -C "$APP_DIR" checkout main
        git -C "$APP_DIR" pull --ff-only >/dev/null 2>&1 || true
    else
        rm -rf "$APP_DIR"
        msg "Downloading DR-VPN (${version})…"
        git clone --depth 1 --branch "$version" "$REPO_URL" "$APP_DIR" 2>/dev/null \
            || { err "Failed to clone the repository."; exit 1; }
    fi

    # --- python env
    msg "Installing Python 3.14 and dependencies (this may take a minute)…"
    (cd "$APP_DIR" && uv sync -q)

    # --- env file
    if [[ ! -f "$APP_DIR/.env" ]]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    fi
    chmod 600 "$APP_DIR/.env"
    sed -i "s|^#\? *UVICORN_PORT *=.*|UVICORN_PORT = ${port}|" "$APP_DIR/.env"
    grep -q "^UVICORN_PORT" "$APP_DIR/.env" || echo "UVICORN_PORT = ${port}" >> "$APP_DIR/.env"

    # --- resolve database URL
    local active_db_url=""
    if [[ -n "$db_url" ]]; then
        active_db_url="$db_url"
        msg "Using the provided database URL."
    else
        case "$db" in
            sqlite)
                active_db_url="sqlite+aiosqlite:///${DATA_DIR}/${DB_FILE_NAME}"
                ;;
            postgresql)
                local pg_pass; pg_pass="$(rand_password)"
                active_db_url="postgresql+asyncpg://drvpn:${pg_pass}@localhost:5432/drvpn"
                warn "PostgreSQL chosen: create the 'drvpn' database/user with password '${pg_pass}' (or edit $APP_DIR/.env afterwards)."
                ;;
            mysql)
                local my_pass; my_pass="$(rand_password)"
                active_db_url="mysql+asyncmy://drvpn:${my_pass}@localhost:3306/drvpn"
                warn "MySQL chosen: create the 'drvpn' database/user with password '${my_pass}' (or edit $APP_DIR/.env afterwards)."
                ;;
            *) err "Unsupported --database '$db' (use sqlite | postgresql | mysql, or --db-url)."; exit 1 ;;
        esac
    fi

    # normalize: comment out every existing URL line, then write the active one (idempotent)
    mkdir -p "$DATA_DIR" "$BACKUP_DIR"
    sed -i 's|^\(# \)\?SQLALCHEMY_DATABASE_URL.*|# SQLALCHEMY_DATABASE_URL (active value appended below)|' "$APP_DIR/.env"
    echo "SQLALCHEMY_DATABASE_URL = \"${active_db_url}\"" >> "$APP_DIR/.env"

    # --- migrations
    msg "Running database migrations…"
    (cd "$APP_DIR" && uv run alembic upgrade head -q) || { err "Migrations failed."; exit 1; }

    # --- systemd service
    msg "Creating systemd service…"
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=DR-VPN panel
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python main.py
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

# reasonable hardening
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now "$SERVICE_NAME" >/dev/null 2>&1

    # --- CLI wrapper
    cat > /usr/local/bin/drvpn <<'WRAPPER'
#!/usr/bin/env bash
exec bash /opt/dr-vpn/scripts/drvpn.sh "$@"
WRAPPER
    chmod +x /usr/local/bin/drvpn

    # wait for boot
    msg "Waiting for the panel to start…"
    local host="127.0.0.1"
    for _ in $(seq 1 30); do
        if curl -sf "http://${host}:${port}/health" >/dev/null 2>&1; then break; fi
        sleep 1
    done

    # --- SSL (optional)
    if [[ -n "$ssl_domain" ]]; then
        setup_ssl "$ssl_domain" "$port"
    else
        warn "No SSL configured: the panel only accepts localhost connections."
        warn "Re-install with --ssl-domain <domain>, or use an SSH tunnel for now:"
        warn "    ssh -L ${port}:localhost:${port} user@server"
    fi

    # --- temp key + summary
    local temp_key
    temp_key="$(bash "$0" cli generate-temp-key 2>/dev/null | tail -1)"
    echo
    echo -e "${BOLD}${GREEN}=============================================="
    echo -e " DR-VPN installed successfully!"
    echo -e "${GREEN}==============================================${NC}"
    echo -e " Service:      systemctl ${GREEN}status ${SERVICE_NAME}${NC}"
    echo -e " Files:        ${APP_DIR}"
    echo -e " Data:         ${DATA_DIR}"
    echo -e " Config:       ${APP_DIR}/.env"
    if [[ -n "$ssl_domain" ]]; then
        echo -e " Dashboard:    ${CYAN}https://${ssl_domain}:${port}/dashboard/${NC}"
    else
        echo -e " Dashboard:    ${CYAN}http://localhost:${port}/dashboard/${NC}  (localhost only — see SSL note above)"
    fi
    if [[ -n "$temp_key" ]]; then
        echo -e " Setup key:    ${BOLD}${YELLOW}${temp_key}${NC}"
        echo -e "               (one-time key — open the dashboard and use it to create the owner account)"
    fi
    echo -e " CLI:          ${GREEN}drvpn cli generate-temp-key${NC} · ${GREEN}drvpn status${NC} · ${GREEN}drvpn help${NC}"
    echo -e "${BOLD}${GREEN}==============================================${NC}"
}

setup_ssl() {
    local domain="$1" panel_port="$2"
    msg "Setting up SSL certificate for ${domain} (acme.sh, standalone HTTP)…"
    apt_install socat openssl >/dev/null 2>&1 || true
    local acme="$HOME/.acme.sh/acme.sh"
    [[ -f "$acme" ]] || curl -s https://get.acme.sh | sh -s email="admin@${domain}" >/dev/null 2>&1
    local cert_dir="${DATA_DIR}/certs/${domain}"
    mkdir -p "$cert_dir"
    if ! "$acme" --issue -d "$domain" --standalone --httpport 8090 --server letsencrypt \
        --key-file "$cert_dir/key.pem" --fullchain-file "$cert_dir/cert.pem" --force; then
        err "Certificate issuance failed (is port 8090 reachable from the internet and DNS pointing here?)."
        return 1
    fi
    sed -i "s|^#\? *UVICORN_SSL_CERTFILE *=.*|UVICORN_SSL_CERTFILE = \"${cert_dir}/cert.pem\"|" "$APP_DIR/.env"
    sed -i "s|^#\? *UVICORN_SSL_KEYFILE *=.*|UVICORN_SSL_KEYFILE = \"${cert_dir}/key.pem\"|"  "$APP_DIR/.env"
    grep -q "^UVICORN_SSL_CERTFILE" "$APP_DIR/.env" || echo "UVICORN_SSL_CERTFILE = \"${cert_dir}/cert.pem\"" >> "$APP_DIR/.env"
    grep -q "^UVICORN_SSL_KEYFILE"  "$APP_DIR/.env" || echo "UVICORN_SSL_KEYFILE = \"${cert_dir}/key.pem\""  >> "$APP_DIR/.env"
    systemctl restart "$SERVICE_NAME"
    (crontab -l 2>/dev/null | grep -v "$acme.*--domain ${domain}"; \
     echo "0 3 * * * $acme --issue -d ${domain} --standalone --httpport 8090 --server letsencrypt --key-file ${cert_dir}/key.pem --fullchain-file ${cert_dir}/cert.pem --force && systemctl restart ${SERVICE_NAME}") | crontab -
    msg "SSL certificate installed; renewal cron added (03:00 daily check)."
}

# ----------------------------- update ---------------------------------------

update_command() {
    require_root
    [[ -d "$APP_DIR/.git" ]] || { err "DR-VPN is not installed at $APP_DIR."; exit 1; }
    msg "Backing up before update…"
    backup_command --quiet || true
    msg "Updating source…"
    git -C "$APP_DIR" fetch --tags --force
    git -C "$APP_DIR" pull --ff-only
    msg "Syncing dependencies…"
    (cd "$APP_DIR" && uv sync -q)
    msg "Running migrations…"
    (cd "$APP_DIR" && uv run alembic upgrade head -q)
    msg "Restarting service…"
    systemctl restart "$SERVICE_NAME"
    sleep 3
    if service_running; then
        msg "DR-VPN updated to $(panel_version)."
    else
        err "Service failed to start after update — check: journalctl -u ${SERVICE_NAME} -n 50"
        exit 1
    fi
}

# ----------------------------- uninstall ------------------------------------

uninstall_command() {
    require_root
    msg "Stopping and disabling the service…"
    systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload
    rm -f /usr/local/bin/drvpn
    if [[ "$1" != "--purge" ]]; then
        read -rp "Delete application files ($APP_DIR), database and backups? Type 'purge' to confirm, anything else to keep: " reply
        [[ "$reply" == "purge" ]] || { msg "Files kept. Service removed."; return 0; }
    fi
    rm -rf "$APP_DIR" "$DATA_DIR" "$BACKUP_DIR"
    msg "DR-VPN fully removed."
}

# ----------------------------- backup/restore -------------------------------

backup_command() {
    [[ -f "$APP_DIR/$DB_FILE_NAME" || -f "$DATA_DIR/$DB_FILE_NAME" ]] || { err "Nothing to back up (no database found)."; exit 1; }
    local ts file
    ts="$(date +%Y%m%d-%H%M%S)"
    file="${BACKUP_DIR}/drvpn-backup-${ts}.tar.gz"
    mkdir -p "$BACKUP_DIR"
    tar -czf "$file" -C / \
        $( [[ -f "$APP_DIR/$DB_FILE_NAME" ]] && echo "opt/dr-vpn/$DB_FILE_NAME" ) \
        $( [[ -f "$DATA_DIR/$DB_FILE_NAME" ]] && echo "var/lib/dr-vpn/$DB_FILE_NAME" ) \
        opt/dr-vpn/.env 2>/dev/null || true
    msg "Backup written to ${file}"
    [[ "$1" == "--quiet" ]] || echo "$file"
}

restore_command() {
    require_root
    local file="$1"
    [[ -f "$file" ]] || { err "Backup file not found: $file"; exit 1; }
    msg "Stopping service…"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    msg "Restoring from $file …"
    tar -xzf "$file" -C /
    systemctl start "$SERVICE_NAME"
    sleep 3
    service_running && msg "Restore complete — service is running." \
        || { err "Service did not start — check journalctl -u ${SERVICE_NAME}"; exit 1; }
}

# ----------------------------- service commands -----------------------------

status_command() {
    echo -e "${BOLD}DR-VPN $(panel_version)${NC} — $APP_DIR"
    systemctl --no-pager status "$SERVICE_NAME" 2>/dev/null || warn "Service is not installed."
    local port
    port="$(grep -oE 'UVICORN_PORT *= *[0-9]+' "$APP_DIR/.env" 2>/dev/null | grep -oE '[0-9]+' | head -1 || echo 8000)"
    if curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
        echo -e "${GREEN}Health check: OK${NC} (http://127.0.0.1:${port}/health)"
    else
        warn "Health check: no response on port ${port}"
    fi
}

logs_command()       { journalctl -u "$SERVICE_NAME" "$@"; }
restart_command()    { require_root; systemctl restart "$SERVICE_NAME"; msg "DR-VPN restarted."; }
stop_command()       { require_root; systemctl stop "$SERVICE_NAME"; msg "DR-VPN stopped."; }
start_command()      { require_root; systemctl start "$SERVICE_NAME"; msg "DR-VPN started."; }

cli_command() {
    [[ -d "$APP_DIR" ]] || { err "DR-VPN is not installed."; exit 1; }
    (cd "$APP_DIR" && uv run python drvpn-cli.py "$@")
}

edit_env_command() {
    "${EDITOR:-nano}" "$APP_DIR/.env"
    msg "Restart the service to apply changes: drvpn restart"
}

version_command() {
    echo "DR-VPN $(panel_version)"
}

# ----------------------------- dispatcher -----------------------------------

usage() {
    cat <<USAGE
DR-VPN manager

Usage: drvpn <command> [options]

Commands:
  install     Install DR-VPN (options: --database sqlite|postgresql|mysql,
              --db-url URL, --port N, --ssl-domain DOMAIN, --version X.Y.Z, --yes)
  update      Update to the latest version (backs up first)
  uninstall   Remove the service (add --purge to also delete files)
  status      Show service status and health check
  logs [args] Follow/view service logs (journalctl passthrough)
  start|stop|restart   Manage the systemd service
  backup      Create a backup archive (database + .env)
  restore FILE  Restore from a backup archive
  cli [args]  Run the DR-VPN CLI (e.g. cli generate-temp-key)
  edit-env    Open .env in an editor
  version     Print the installed version
  help        Show this help

One-line install:
  sudo bash -c "\$(curl -fsSL ${RAW_URL})" @ install
USAGE
}

main() {
    local cmd="${1:-help}"
    shift || true
    case "$cmd" in
        install)  install_command "$@" ;;
        update)   update_command "$@" ;;
        uninstall) uninstall_command "$@" ;;
        status)   status_command ;;
        logs)     logs_command "$@" ;;
        start)    start_command ;;
        stop)     stop_command ;;
        restart)  restart_command ;;
        backup)   backup_command "$@" ;;
        restore)  [[ $# -ge 1 ]] || { err "usage: drvpn restore FILE"; exit 1; }; restore_command "$@" ;;
        cli)      cli_command "$@" ;;
        edit-env) edit_env_command ;;
        version)  version_command ;;
        help|-h|--help) usage ;;
        *) err "Unknown command: $cmd"; usage; exit 1 ;;
    esac
}

main "$@"
