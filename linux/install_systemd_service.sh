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
Environment=PUBLIC_MAX_CONNECTIONS=16
Environment=PUBLIC_UPSTREAM_RETRIES=12
Environment=PUBLIC_STREAM_RETRIES=4
Environment=PUBLIC_CLIENT_FAILOVER_ATTEMPTS=4
Environment=PUBLIC_CLIENT_FAILOVER_WAIT_SECONDS=120
Environment=PUBLIC_CONNECT_FAILURES_BEFORE_ROTATE=1
Environment=HEALTH_INTERVAL=120
Environment=HEALTH_FAILURES=5
Environment=HEALTH_PROBES=3
Environment=HEALTH_PROBE_MAX_FAILURES=1
Environment=SKIP_HEALTH_WHEN_PUBLIC_ACTIVE_SECONDS=300
Environment=DEFER_ROTATE_WHEN_PUBLIC_ACTIVE_SECONDS=300
Environment=MAX_ROTATE_DEFER_SECONDS=900
Environment=HEALTH_VIA_PUBLIC=0
Environment=RECONNECT_DELAY=10
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
