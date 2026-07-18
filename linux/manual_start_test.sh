#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/JumpProxyLinuxWine"
SDK_DIR="${ROOT}/win_jump_install/bin"
SDK_EXE="${SDK_DIR}/xvpnsdk.exe"
RUNTIME="${ROOT}/WinProxy/runtime"
PREFIX="${ROOT}/.wine-xvpn"
BASE="http://127.0.0.1:8701"
SOCKS_PORT="${SOCKS_PORT:-55412}"

cd "${ROOT}"
mkdir -p "${RUNTIME}" "${PREFIX}/drive_c/windows/system32"

WINEPREFIX="${PREFIX}" wineserver -k >/dev/null 2>&1 || true
cp -f "${SDK_DIR}/iphlpapi.dll" "${PREFIX}/drive_c/windows/system32/iphlpapi.dll"
cp -f "${SDK_DIR}/wintun.dll" "${PREFIX}/drive_c/windows/system32/wintun.dll"

(
  cd "${SDK_DIR}"
  env \
    WINEPREFIX="${PREFIX}" \
    WINEDLLOVERRIDES="iphlpapi,wintun=n,b" \
    WINEDEBUG="-all" \
    wine "${SDK_EXE}" -http_addr "127.0.0.1:8701"
) >"${RUNTIME}/sdk_manual.log" 2>&1 &
echo "$!" >"${RUNTIME}/sdk_manual.pid"

for _ in $(seq 1 100); do
  if curl -fsS -X POST -H 'Content-Type: application/json' --data '{}' "${BASE}/api/stat" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

echo "--- stat ---"
curl -sS -X POST -H 'Content-Type: application/json' --data '{}' "${BASE}/api/stat" | head -c 500 || true
echo

echo "--- start ---"
curl -sS -m 60 -X POST -H 'Content-Type: application/json' --data-binary @"${RUNTIME}/native_start_payload.json" "${BASE}/api/proxy_connector_start" || true
echo

echo "--- ports immediately ---"
ss -ltnp | grep -E ':55412|:8701|:10880' || true

echo "--- local socks curl ---"
curl --socks5-hostname "127.0.0.1:${SOCKS_PORT}" --max-time 8 http://ifconfig.me/ip || true
echo

echo "--- ports after curl ---"
ss -ltnp | grep -E ':55412|:8701|:10880' || true

echo "--- sdk tail ---"
tail -120 "${RUNTIME}/sdk_manual.log" || true
