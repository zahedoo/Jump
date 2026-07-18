#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

APP_NAME="JumpProxy"
SERVICE_NAME="${SERVICE_NAME:-jumpproxy}"
DEFAULT_INSTALL_DIR="/opt/JumpProxyLinuxWine"
INSTALL_DIR="${TARGET_DIR:-${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-/etc/jumpproxy.env}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

PUBLIC_PORT="${PUBLIC_PORT:-10880}"
PUBLIC_LISTEN="${PUBLIC_LISTEN:-0.0.0.0}"
MODE="${MODE:-ad}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-120}"
HEALTH_FAILURES="${HEALTH_FAILURES:-5}"
DIRECT_FALLBACK="${DIRECT_FALLBACK:-1}"
ALLOW_FIREWALL=0
INSTALL_DEPS=1
START_SERVICE=1
RUN_TEST=1
SKIP_RUNTIME_CHECK=0
YES=0
ACTION="install"

log() { printf '\033[1;32m[+] %s\033[0m\n' "$*"; }
info() { printf '\033[1;34m[i] %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*" >&2; }
die() { printf '\033[1;31m[ERROR] %s\033[0m\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
${APP_NAME} professional installer

Usage:
  sudo bash install.sh [options]

Main install:
  sudo bash install.sh
  sudo bash install.sh --port 10880 --mode ad --allow-firewall
  sudo bash install.sh --install-dir /opt/JumpProxyLinuxWine --no-start

Operations:
  --install              Install/update package and systemd service (default)
  --status               Show service, ports, and active config
  --logs                 Follow service logs
  --test                 Test the local SOCKS endpoint
  --restart              Restart service
  --uninstall            Disable/remove systemd service only
  --purge                With --uninstall, also remove install dir and env file

Options:
  --install-dir PATH     Install directory (default: ${DEFAULT_INSTALL_DIR})
  --port PORT            Public SOCKS5 port (default: 10880)
  --listen IP            Public listen address (default: 0.0.0.0)
  --mode MODE            ad|ads|normal|smart|all|adonly (default: ad)
  --allow-firewall       Open the public port with ufw/firewalld when available
  --skip-deps            Do not install apt/Wine dependencies
  --skip-runtime-check   Do not stop if private runtime binaries are missing
  --no-start             Install but do not start/restart service
  --no-test              Do not run post-install curl test
  -y, --yes              Non-interactive confirmation for uninstall/purge
  -h, --help             Show this help

Runtime files expected after extraction/copy:
  win_jump_install/bin/xvpnsdk.exe
  win_jump_install/bin/iphlpapi.dll
  win_jump_install/bin/fwpuclnt.dll
  win_jump_install/bin/wintun.dll
  win_jump_install/bin/assets/geoip.dat
  win_jump_install/bin/assets/geosite.dat

After install:
  sudo systemctl status ${SERVICE_NAME}
  sudo journalctl -u ${SERVICE_NAME} -f
  curl --socks5-hostname 127.0.0.1:${PUBLIC_PORT} http://ifconfig.me/ip
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install) ACTION="install"; shift ;;
    --status) ACTION="status"; shift ;;
    --logs) ACTION="logs"; shift ;;
    --test) ACTION="test"; shift ;;
    --restart) ACTION="restart"; shift ;;
    --uninstall) ACTION="uninstall"; shift ;;
    --purge) ACTION="uninstall"; PURGE=1; shift ;;
    --install-dir|--target-dir) INSTALL_DIR="$2"; shift 2 ;;
    --port|--public-port) PUBLIC_PORT="$2"; shift 2 ;;
    --listen|--public-listen) PUBLIC_LISTEN="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --allow-firewall) ALLOW_FIREWALL=1; shift ;;
    --skip-deps) INSTALL_DEPS=0; shift ;;
    --skip-runtime-check) SKIP_RUNTIME_CHECK=1; shift ;;
    --no-start) START_SERVICE=0; shift ;;
    --no-test) RUN_TEST=0; shift ;;
    -y|--yes) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1. Use --help." ;;
  esac
done

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    die "Run as root: sudo bash install.sh $ACTION"
  fi
}

load_env_if_exists() {
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE" || true
  fi
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

install_dependencies() {
  if [[ "$INSTALL_DEPS" != "1" ]]; then
    warn "Skipping dependency installation (--skip-deps)."
    return
  fi
  need_command apt-get

  log "Installing base dependencies ..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl gnupg unzip python3 iproute2 procps psmisc lsof tar

  if command -v wine >/dev/null 2>&1 || command -v wine64 >/dev/null 2>&1; then
    info "Wine already installed."
    return
  fi

  log "Installing Wine/WineHQ runtime ..."
  dpkg --add-architecture i386 || true
  mkdir -pm755 /etc/apt/keyrings
  curl -fsSL https://dl.winehq.org/wine-builds/winehq.key -o /etc/apt/keyrings/winehq-archive.key || true

  # shellcheck disable=SC1091
  . /etc/os-release
  local distro="${ID:-}"
  local like="${ID_LIKE:-}"
  local codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
  local source_installed=0

  if [[ "$distro" == "ubuntu" || "$distro" == "linuxmint" || "$like" == *"ubuntu"* ]]; then
    codename="${UBUNTU_CODENAME:-${codename:-jammy}}"
    curl -fsSL "https://dl.winehq.org/wine-builds/ubuntu/dists/${codename}/winehq-${codename}.sources" \
      -o "/etc/apt/sources.list.d/winehq-${codename}.sources" && source_installed=1 || true
  elif [[ "$distro" == "debian" || "$like" == *"debian"* ]]; then
    codename="${codename:-bookworm}"
    curl -fsSL "https://dl.winehq.org/wine-builds/debian/dists/${codename}/winehq-${codename}.sources" \
      -o "/etc/apt/sources.list.d/winehq-${codename}.sources" && source_installed=1 || true
  fi

  if [[ "$source_installed" == "1" ]]; then
    apt-get update || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y --install-recommends winehq-staging && return
    warn "WineHQ staging install failed; falling back to distro Wine packages."
  fi

  DEBIAN_FRONTEND=noninteractive apt-get install -y wine wine64 winbind || \
    DEBIAN_FRONTEND=noninteractive apt-get install -y wine64 winbind
}

copy_package() {
  if [[ "$SRC_DIR" == "$INSTALL_DIR" ]]; then
    info "Source is already the install directory: $INSTALL_DIR"
    return
  fi

  log "Copying package to $INSTALL_DIR ..."
  mkdir -p "$INSTALL_DIR"

  local items=()
  for item in install.sh run.sh telegram_config.example.json WinProxy linux win_jump_install; do
    [[ -e "$SRC_DIR/$item" ]] && items+=("$item")
  done
  for item in README.md README_INSTALL_FA.md README_JumpProxyLinuxFinal.md; do
    [[ -f "$SRC_DIR/$item" ]] && items+=("$item")
  done
  [[ "${#items[@]}" -gt 0 ]] || die "No package files found in $SRC_DIR"

  tar -C "$SRC_DIR" \
    --exclude='./.git' \
    --exclude='./WinProxy/runtime' \
    --exclude='./build' \
    --exclude='./dist' \
    --exclude='./telegram_config.json' \
    --exclude='./*.log' \
    --exclude='./*.db' \
    --exclude='./*.sqlite' \
    --exclude='./*.sqlite3' \
    --exclude='./plink_*' \
    --exclude='./.ssh_known_hosts*' \
    -cf - "${items[@]}" | tar -C "$INSTALL_DIR" -xf -
}

validate_runtime() {
  local required=(
    "WinProxy/jumpjump_native_proxy.py"
    "linux/run_xvpn_wine_proxy.sh"
    "win_jump_install/bin/xvpnsdk.exe"
    "win_jump_install/bin/iphlpapi.dll"
    "win_jump_install/bin/fwpuclnt.dll"
    "win_jump_install/bin/wintun.dll"
    "win_jump_install/bin/assets/geoip.dat"
    "win_jump_install/bin/assets/geosite.dat"
  )
  local missing=()
  local file
  for file in "${required[@]}"; do
    [[ -f "$INSTALL_DIR/$file" ]] || missing+=("$file")
  done

  if [[ "${#missing[@]}" -gt 0 ]]; then
    warn "Missing runtime files:"
    printf '  - %s\n' "${missing[@]}" >&2
    cat >&2 <<EOF

If you installed from the public GitHub repository, copy your private runtime files to:
  ${INSTALL_DIR}/win_jump_install/bin/
  ${INSTALL_DIR}/win_jump_install/bin/assets/

Then run:
  sudo bash ${INSTALL_DIR}/install.sh --skip-deps

EOF
    [[ "$SKIP_RUNTIME_CHECK" == "1" ]] || die "Runtime validation failed. Use --skip-runtime-check only for source-only setup."
  fi
}

write_environment_file() {
  log "Writing environment config: $ENV_FILE"
  cat >"$ENV_FILE" <<EOF
# ${APP_NAME} service configuration
INSTALL_DIR=${INSTALL_DIR}
PUBLIC_PORT=${PUBLIC_PORT}
PUBLIC_LISTEN=${PUBLIC_LISTEN}
MODE=${MODE}
HEALTH_INTERVAL=${HEALTH_INTERVAL}
HEALTH_FAILURES=${HEALTH_FAILURES}
HEALTH_PROBES=3
HEALTH_PROBE_MAX_FAILURES=1
RECONNECT_DELAY=10
START_WAIT=45
STABILITY_PROBES=2
STABILITY_MAX_FAILURES=1
PUBLIC_MAX_CONNECTIONS=16
PUBLIC_UPSTREAM_RETRIES=12
PUBLIC_STREAM_RETRIES=4
PUBLIC_CLIENT_FAILOVER_ATTEMPTS=4
PUBLIC_CLIENT_FAILOVER_WAIT_SECONDS=120
PUBLIC_CONNECT_FAILURES_BEFORE_ROTATE=1
DIRECT_FALLBACK=${DIRECT_FALLBACK}
SKIP_HEALTH_WHEN_PUBLIC_ACTIVE_SECONDS=300
DEFER_ROTATE_WHEN_PUBLIC_ACTIVE_SECONDS=300
MAX_ROTATE_DEFER_SECONDS=900
HEALTH_VIA_PUBLIC=0
XVPN_DISABLE_UDP=1
XVPN_WINE_DLL_OVERRIDES=iphlpapi,fwpuclnt=n,b
EOF
  chmod 0644 "$ENV_FILE"
}

write_systemd_service() {
  log "Installing systemd service: $SERVICE_FILE"
  cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=JumpProxy XVPN SDK public SOCKS relay
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=-${ENV_FILE}
ExecStart=/bin/bash ${INSTALL_DIR}/linux/run_xvpn_wine_proxy.sh --with-tun2socks --with-iphlpapi-shim
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=20
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME.service"
}

prepare_runtime() {
  log "Preparing runtime permissions and loopback compatibility IP ..."
  chmod +x "$INSTALL_DIR"/linux/*.sh "$INSTALL_DIR"/run.sh 2>/dev/null || true
  mkdir -p "$INSTALL_DIR/WinProxy/runtime"
  ip addr add 172.19.0.1/30 dev lo >/dev/null 2>&1 || true
}

configure_firewall() {
  [[ "$ALLOW_FIREWALL" == "1" ]] || return
  log "Opening TCP port $PUBLIC_PORT in local firewall when available ..."
  if command -v ufw >/dev/null 2>&1; then
    ufw allow "${PUBLIC_PORT}/tcp" || true
  elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port="${PUBLIC_PORT}/tcp" || true
    firewall-cmd --reload || true
  else
    warn "No ufw/firewalld found. Open TCP ${PUBLIC_PORT} in your provider/security-group firewall."
  fi
}

start_service() {
  [[ "$START_SERVICE" == "1" ]] || { warn "Service not started (--no-start)."; return; }
  log "Starting/restarting $SERVICE_NAME ..."
  systemctl restart "$SERVICE_NAME.service"
  sleep 3
  systemctl --no-pager --full status "$SERVICE_NAME.service" | sed -n '1,16p' || true
}

run_test() {
  local port="${1:-$PUBLIC_PORT}"
  log "Testing local SOCKS endpoint on 127.0.0.1:${port} ..."
  local ok=0
  local i
  for i in $(seq 1 18); do
    if curl --socks5-hostname "127.0.0.1:${port}" --connect-timeout 8 --max-time 20 -fsS http://ifconfig.me/ip; then
      ok=1
      break
    fi
    sleep 5
  done
  if [[ "$ok" == "1" ]]; then
    echo
    log "SOCKS test passed."
  else
    warn "SOCKS test did not pass yet. Check logs: sudo journalctl -u ${SERVICE_NAME} -f"
  fi
}

show_status() {
  load_env_if_exists
  echo "== systemd =="
  systemctl --no-pager --full status "$SERVICE_NAME.service" | sed -n '1,22p' || true
  echo
  echo "== listening ports =="
  ss -lntp 2>/dev/null | grep -E ":(${PUBLIC_PORT}|55412|8701)\b" || true
  echo
  echo "== active state =="
  python3 - <<PY 2>/dev/null || true
import json
p="${INSTALL_DIR}/WinProxy/runtime/active_state.json"
try:
    s=json.load(open(p))
    sel=s.get("selected") or {}
    print("status=", s.get("status"))
    print("mode=", s.get("mode"))
    print("purpose=", sel.get("purpose"))
    print("id=", sel.get("id"))
    print("remote=", f"{sel.get('host')}:{sel.get('port')}")
    print("publicIp=", s.get("publicIp"))
    print("socks=", s.get("socks"))
except Exception as exc:
    print("active_state unavailable:", exc)
PY
}

follow_logs() {
  journalctl -u "$SERVICE_NAME.service" -f
}

restart_service() {
  require_root
  systemctl restart "$SERVICE_NAME.service"
  show_status
}

uninstall_service() {
  require_root
  if [[ "${YES:-0}" != "1" ]]; then
    read -r -p "Remove ${SERVICE_NAME} service? [y/N] " ans
    [[ "$ans" == "y" || "$ans" == "Y" ]] || die "Cancelled."
  fi
  systemctl stop "$SERVICE_NAME.service" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME.service" 2>/dev/null || true
  rm -f "$SERVICE_FILE"
  systemctl daemon-reload
  log "Service removed."
  if [[ "${PURGE:-0}" == "1" ]]; then
    [[ "$INSTALL_DIR" == "/" || -z "$INSTALL_DIR" ]] && die "Refusing to purge unsafe install dir."
    rm -rf "$INSTALL_DIR"
    rm -f "$ENV_FILE"
    log "Purged $INSTALL_DIR and $ENV_FILE"
  fi
}

install_all() {
  require_root
  install_dependencies
  copy_package
  validate_runtime
  prepare_runtime
  write_environment_file
  write_systemd_service
  configure_firewall
  start_service
  [[ "$RUN_TEST" == "1" && "$START_SERVICE" == "1" ]] && run_test "$PUBLIC_PORT"

  cat <<EOF

Install complete.

Public SOCKS5:
  ${PUBLIC_LISTEN}:${PUBLIC_PORT}

Useful commands:
  sudo systemctl restart ${SERVICE_NAME}
  sudo systemctl status ${SERVICE_NAME} --no-pager
  sudo journalctl -u ${SERVICE_NAME} -f
  sudo bash ${INSTALL_DIR}/install.sh --status
  sudo bash ${INSTALL_DIR}/install.sh --test

External test:
  curl --socks5-hostname SERVER_IP:${PUBLIC_PORT} http://ifconfig.me/ip

Config:
  ${ENV_FILE}

EOF
}

case "$ACTION" in
  install) install_all ;;
  status) show_status ;;
  logs) follow_logs ;;
  test) load_env_if_exists; run_test "$PUBLIC_PORT" ;;
  restart) restart_service ;;
  uninstall) uninstall_service ;;
  *) die "Unsupported action: $ACTION" ;;
esac
