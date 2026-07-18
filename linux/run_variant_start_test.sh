#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/JumpProxyLinuxWine"
PREFIX="${ROOT}/.wine-xvpn"
SDK_DIR="${ROOT}/win_jump_install/bin"
RUNTIME="${ROOT}/WinProxy/runtime"
BASE="http://127.0.0.1:8701"

cd "${ROOT}"
mkdir -p "${RUNTIME}" "${PREFIX}/drive_c/windows/system32"
WINEPREFIX="${PREFIX}" wineserver -k >/dev/null 2>&1 || true
cp -f "${SDK_DIR}/iphlpapi.dll" "${PREFIX}/drive_c/windows/system32/iphlpapi.dll"
cp -f "${SDK_DIR}/wintun.dll" "${PREFIX}/drive_c/windows/system32/wintun.dll"

(
  cd "${SDK_DIR}"
  env WINEPREFIX="${PREFIX}" WINEDLLOVERRIDES="iphlpapi=n,b" WINEDEBUG="-all" \
    wine "${SDK_DIR}/xvpnsdk.exe" -http_addr "127.0.0.1:8701"
) >"${RUNTIME}/sdk_variant.log" 2>&1 &
echo "$!" >"${RUNTIME}/sdk_variant.pid"

for _ in $(seq 1 100); do
  curl -fsS -X POST -H 'Content-Type: application/json' --data '{}' "${BASE}/api/stat" >/dev/null 2>&1 && break
  sleep 0.25
done

echo "--- stat ---"
curl -sS -X POST -H 'Content-Type: application/json' --data '{}' "${BASE}/api/stat" | head -c 300 || true
echo

python3 "${ROOT}/linux/variant_start_test.py"

echo "--- sdk tail ---"
tail -80 "${RUNTIME}/sdk_variant.log" || true
