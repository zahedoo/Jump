#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo/root: sudo $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-jump-proxy-xvpn}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-root}}"
PUBLIC_PORT="${PUBLIC_PORT:-10880}"
MODE="${MODE:-ad}"
WINEPREFIX="${WINEPREFIX:-${ROOT}/.wine-xvpn}"

if [[ ! -x "${SCRIPT_DIR}/run_xvpn_wine_proxy.sh" ]]; then
  chmod +x "${SCRIPT_DIR}/run_xvpn_wine_proxy.sh"
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat >"${SERVICE_FILE}" <<EOF
[Unit]
Description=JumpProxy XVPN SDK through Wine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${ROOT}
Environment=PUBLIC_PORT=${PUBLIC_PORT}
Environment=MODE=${MODE}
Environment=WINEPREFIX=${WINEPREFIX}
Environment=PUBLIC_MAX_CONNECTIONS=8
Environment=HEALTH_INTERVAL=30
Environment=HEALTH_FAILURES=1
Environment=RECONNECT_DELAY=5
ExecStart=${SCRIPT_DIR}/run_xvpn_wine_proxy.sh
Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

echo "Installed: ${SERVICE_FILE}"
echo ""
echo "Start:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo ""
echo "Logs:"
echo "  journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "Status:"
echo "  systemctl status ${SERVICE_NAME} --no-pager"

