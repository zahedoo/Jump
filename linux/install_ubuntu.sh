#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WINEPREFIX="${WINEPREFIX:-${ROOT}/.wine-xvpn}"

if [[ "$(id -u)" -ne 0 ]]; then
  SUDO=sudo
else
  SUDO=
fi

echo "Installing Ubuntu dependencies for JumpProxy Linux/Wine ..."
${SUDO} apt-get update
${SUDO} env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates \
  curl \
  procps \
  python3 \
  unzip \
  wine \
  wine64 \
  winbind || {
    echo "Base Wine package names failed. Trying minimal fallback packages ..." >&2
    ${SUDO} env DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl procps python3 unzip wine64 winbind
  }

chmod +x "${SCRIPT_DIR}/run_xvpn_wine_proxy.sh" \
  "${SCRIPT_DIR}/install_systemd_service.sh" \
  "${SCRIPT_DIR}/test_public_proxy.sh" 2>/dev/null || true

mkdir -p "${WINEPREFIX}"
export WINEPREFIX
export WINEDEBUG="${WINEDEBUG:--all}"

if command -v wineboot >/dev/null 2>&1; then
  echo "Initializing Wine prefix: ${WINEPREFIX}"
  wineboot -u >/dev/null 2>&1 || true
fi

echo "Install complete."
echo ""
echo "Run:"
echo "  ${SCRIPT_DIR}/run_xvpn_wine_proxy.sh --public-port 10880 --mode ad"
echo ""
echo "Install as systemd service:"
echo "  sudo ${SCRIPT_DIR}/install_systemd_service.sh"
