#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_DIR="${TARGET_DIR:-/opt/JumpProxyLinuxWine}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(id -u)" != "0" ]]; then
  echo "ERROR: run as root: sudo bash install.sh" >&2
  exit 1
fi

echo "Installing system dependencies ..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl gnupg unzip python3 iproute2 procps \
  gcc-mingw-w64-x86-64

if ! command -v wine >/dev/null 2>&1; then
  echo "Installing WineHQ staging ..."
  dpkg --add-architecture i386 || true
  mkdir -pm755 /etc/apt/keyrings
  curl -fsSL https://dl.winehq.org/wine-builds/winehq.key -o /etc/apt/keyrings/winehq-archive.key
  . /etc/os-release
  codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-jammy}}"
  if [[ ! -f "/etc/apt/sources.list.d/winehq-${codename}.sources" ]]; then
    curl -fsSL "https://dl.winehq.org/wine-builds/ubuntu/dists/${codename}/winehq-${codename}.sources" \
      -o "/etc/apt/sources.list.d/winehq-${codename}.sources" || true
  fi
  apt-get update || true
  DEBIAN_FRONTEND=noninteractive apt-get install -y --install-recommends winehq-staging || \
    DEBIAN_FRONTEND=noninteractive apt-get install -y wine
fi

if [[ "${SRC_DIR}" != "${TARGET_DIR}" ]]; then
  echo "Copying package to ${TARGET_DIR} ..."
  mkdir -p "${TARGET_DIR}"
  cp -a "${SRC_DIR}/." "${TARGET_DIR}/"
fi

cd "${TARGET_DIR}"
chmod +x linux/*.sh run.sh || true

echo "Preparing loopback TUN compatibility IP ..."
ip addr add 172.19.0.1/30 dev lo >/dev/null 2>&1 || true

echo "Installing systemd service ..."
cp -f linux/jumpproxy.service /etc/systemd/system/jumpproxy.service
systemctl daemon-reload
systemctl enable jumpproxy.service

echo "Done."
echo "Start with: sudo systemctl restart jumpproxy"
echo "Logs:       sudo journalctl -u jumpproxy -f"
echo "Test:       curl --socks5-hostname 127.0.0.1:10880 -i http://ifconfig.me/ip"

