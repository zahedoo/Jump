#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PUBLIC_PORT="${PUBLIC_PORT:-10880}"
PUBLIC_LISTEN="${PUBLIC_LISTEN:-0.0.0.0}"
MODE="${MODE:-ad}"
SDK_PORT="${SDK_PORT:-8701}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-120}"
HEALTH_FAILURES="${HEALTH_FAILURES:-5}"
HEALTH_PROBES="${HEALTH_PROBES:-3}"
HEALTH_PROBE_MAX_FAILURES="${HEALTH_PROBE_MAX_FAILURES:-1}"
HEALTH_PROBE_DELAY_MS="${HEALTH_PROBE_DELAY_MS:-600}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-http://ifconfig.me/ip}"
RECONNECT_DELAY="${RECONNECT_DELAY:-10}"
START_WAIT="${START_WAIT:-20}"
STABILITY_PROBES="${STABILITY_PROBES:-3}"
STABILITY_MAX_FAILURES="${STABILITY_MAX_FAILURES:-0}"
STABILITY_DELAY_MS="${STABILITY_DELAY_MS:-700}"
PUBLIC_MAX_CONNECTIONS="${PUBLIC_MAX_CONNECTIONS:-8}"
PUBLIC_UPSTREAM_RETRIES="${PUBLIC_UPSTREAM_RETRIES:-8}"
PUBLIC_STREAM_RETRIES="${PUBLIC_STREAM_RETRIES:-2}"
PUBLIC_INITIAL_BUFFER_BYTES="${PUBLIC_INITIAL_BUFFER_BYTES:-262144}"
PUBLIC_RELAY_BUFFER_BYTES="${PUBLIC_RELAY_BUFFER_BYTES:-262144}"
PUBLIC_CLIENT_FAILOVER_ATTEMPTS="${PUBLIC_CLIENT_FAILOVER_ATTEMPTS:-4}"
PUBLIC_CLIENT_FAILOVER_WAIT_SECONDS="${PUBLIC_CLIENT_FAILOVER_WAIT_SECONDS:-120}"
PUBLIC_CONNECT_FAILURES_BEFORE_ROTATE="${PUBLIC_CONNECT_FAILURES_BEFORE_ROTATE:-1}"
DIRECT_FALLBACK="${DIRECT_FALLBACK:-1}"
SKIP_HEALTH_WHEN_PUBLIC_ACTIVE_SECONDS="${SKIP_HEALTH_WHEN_PUBLIC_ACTIVE_SECONDS:-300}"
DEFER_ROTATE_WHEN_PUBLIC_ACTIVE_SECONDS="${DEFER_ROTATE_WHEN_PUBLIC_ACTIVE_SECONDS:-300}"
MAX_ROTATE_DEFER_SECONDS="${MAX_ROTATE_DEFER_SECONDS:-900}"
HEALTH_VIA_PUBLIC="${HEALTH_VIA_PUBLIC:-0}"
NO_TUN2SOCKS="${NO_TUN2SOCKS:-1}"
NO_CLEANUP="${NO_CLEANUP:-0}"
XVPN_IPHLPAPI_SHIM="${XVPN_IPHLPAPI_SHIM:-0}"
XVPN_WINE_DLL_OVERRIDES="${XVPN_WINE_DLL_OVERRIDES:-}"
XVPN_DISABLE_UDP="${XVPN_DISABLE_UDP:-1}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
WINE_BIN="${WINE_BIN:-}"
WINEPREFIX="${WINEPREFIX:-${ROOT}/.wine-xvpn}"
WINEDEBUG="${WINEDEBUG:--all}"

SDK_EXE="${SDK_EXE:-${ROOT}/win_jump_install/bin/xvpnsdk.exe}"
SDK_DIR="$(dirname "${SDK_EXE}")"
ASSETS_DIR="${ASSETS_DIR:-${ROOT}/win_jump_install/bin/assets}"
PROXY_SCRIPT="${ROOT}/WinProxy/jumpjump_native_proxy.py"
RUNTIME_DIR="${ROOT}/WinProxy/runtime"
BASE="http://127.0.0.1:${SDK_PORT}"
EXTRA_ARGS=()

usage() {
  cat <<'EOF'
run_xvpn_wine_proxy.sh

Runs the Windows XVPN SDK on Ubuntu through Wine and exposes a public SOCKS5 port.

Common:
  ./linux/run_xvpn_wine_proxy.sh --public-port 10880 --mode ad
  MODE=normal PUBLIC_PORT=10880 ./linux/run_xvpn_wine_proxy.sh

Options:
  --public-port N
  --public-listen IP
  --mode ad|ads|normal|smart|all|adonly
  --sdk-port N
  --reconnect-delay N
  --health-interval N
  --health-failures N
  --public-max-connections N
  --public-health-url URL
  --public-client-failover-attempts N
  --public-client-failover-wait-seconds N
  --public-connect-failures-before-rotate N
  --direct-fallback
  --no-direct-fallback
  --health-via-public
  --with-tun2socks
  --with-iphlpapi-shim
  --no-cleanup

Extra unknown options are passed to WinProxy/jumpjump_native_proxy.py.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --public-port) PUBLIC_PORT="$2"; shift 2 ;;
    --public-listen) PUBLIC_LISTEN="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --sdk-port) SDK_PORT="$2"; BASE="http://127.0.0.1:${SDK_PORT}"; shift 2 ;;
    --reconnect-delay) RECONNECT_DELAY="$2"; shift 2 ;;
    --health-interval) HEALTH_INTERVAL="$2"; shift 2 ;;
    --health-failures) HEALTH_FAILURES="$2"; shift 2 ;;
    --public-max-connections) PUBLIC_MAX_CONNECTIONS="$2"; shift 2 ;;
    --public-health-url) PUBLIC_HEALTH_URL="$2"; shift 2 ;;
    --public-client-failover-attempts) PUBLIC_CLIENT_FAILOVER_ATTEMPTS="$2"; shift 2 ;;
    --public-client-failover-wait-seconds) PUBLIC_CLIENT_FAILOVER_WAIT_SECONDS="$2"; shift 2 ;;
    --public-connect-failures-before-rotate) PUBLIC_CONNECT_FAILURES_BEFORE_ROTATE="$2"; shift 2 ;;
    --direct-fallback) DIRECT_FALLBACK=1; shift ;;
    --no-direct-fallback) DIRECT_FALLBACK=0; shift ;;
    --health-via-public) HEALTH_VIA_PUBLIC=1; shift ;;
    --with-tun2socks) NO_TUN2SOCKS=0; shift ;;
    --with-iphlpapi-shim) XVPN_IPHLPAPI_SHIM=1; shift ;;
    --no-cleanup) NO_CLEANUP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

if [[ -z "${WINE_BIN}" ]]; then
  if command -v wine >/dev/null 2>&1; then
    WINE_BIN="$(command -v wine)"
  elif command -v wine64 >/dev/null 2>&1; then
    WINE_BIN="$(command -v wine64)"
  else
    echo "ERROR: wine/wine64 not found. Run linux/install_ubuntu.sh first." >&2
    exit 1
  fi
fi

for required in "${PYTHON_BIN}" curl; do
  if ! command -v "${required}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${required}" >&2
    exit 1
  fi
done

if [[ ! -f "${SDK_EXE}" ]]; then
  echo "ERROR: missing XVPN SDK: ${SDK_EXE}" >&2
  exit 1
fi
if [[ ! -f "${PROXY_SCRIPT}" ]]; then
  echo "ERROR: missing proxy script: ${PROXY_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${RUNTIME_DIR}" "${WINEPREFIX}"
export WINEPREFIX WINEDEBUG
SYSTEM32_IPHLPAPI="${WINEPREFIX}/drive_c/windows/system32/iphlpapi.dll"

stop_connector() {
  curl -fsS \
    -X POST \
    -H 'Content-Type: application/json' \
    --data '{}' \
    "${BASE}/api/proxy_connector_stop" >/dev/null 2>&1 || true
}

cleanup() {
  local code=$?
  trap - EXIT INT TERM
  stop_connector
  if [[ -n "${SDK_PID:-}" ]]; then
    kill "${SDK_PID}" >/dev/null 2>&1 || true
    wait "${SDK_PID}" >/dev/null 2>&1 || true
  fi
  WINEPREFIX="${WINEPREFIX}" wineserver -k >/dev/null 2>&1 || true
  exit "${code}"
}
trap cleanup EXIT INT TERM

if [[ "${NO_CLEANUP}" != "1" ]]; then
  echo "Cleaning previous Wine SDK/proxy state ..."
  stop_connector
  pkill -f "${PROXY_SCRIPT}.*--base ${BASE}" >/dev/null 2>&1 || true
  WINEPREFIX="${WINEPREFIX}" wineserver -k >/dev/null 2>&1 || true
fi

if [[ "${XVPN_IPHLPAPI_SHIM}" != "1" && -f "${SYSTEM32_IPHLPAPI}" ]]; then
  rm -f "${SYSTEM32_IPHLPAPI}" >/dev/null 2>&1 || true
fi

echo "Preparing Wine prefix: ${WINEPREFIX}"
if command -v wineboot >/dev/null 2>&1; then
  WINEPREFIX="${WINEPREFIX}" wineboot -u >/dev/null 2>&1 || true
fi

SDK_ENV=(WINEPREFIX="${WINEPREFIX}")
if [[ "${XVPN_IPHLPAPI_SHIM}" == "1" ]]; then
  SHIM_DLL="${SDK_DIR}/iphlpapi.dll"
  if [[ ! -f "${SHIM_DLL}" ]]; then
    echo "ERROR: --with-iphlpapi-shim was requested but missing ${SHIM_DLL}." >&2
    echo "Build it with: x86_64-w64-mingw32-gcc -shared -O2 -Wall -Wextra -Wl,--export-all-symbols -o '${SHIM_DLL}' '${ROOT}/linux/iphlpapi_shim.c'" >&2
    exit 1
  fi
  mkdir -p "$(dirname "${SYSTEM32_IPHLPAPI}")"
  cp -f "${SHIM_DLL}" "${SYSTEM32_IPHLPAPI}"
  if [[ -f "${SDK_DIR}/wintun.dll" ]]; then
    cp -f "${SDK_DIR}/wintun.dll" "${WINEPREFIX}/drive_c/windows/system32/wintun.dll"
  fi
  if [[ -f "${SDK_DIR}/fwpuclnt.dll" ]]; then
    cp -f "${SDK_DIR}/fwpuclnt.dll" "${WINEPREFIX}/drive_c/windows/system32/fwpuclnt.dll"
  fi
  if [[ -z "${XVPN_WINE_DLL_OVERRIDES}" ]]; then
    dlls=("iphlpapi")
    if [[ -f "${SDK_DIR}/fwpuclnt.dll" ]]; then
      dlls+=("fwpuclnt")
    fi
    if [[ -f "${SDK_DIR}/wintun.dll" ]]; then
      dlls+=("wintun")
    fi
    XVPN_WINE_DLL_OVERRIDES="$(IFS=,; echo "${dlls[*]}")=n,b"
  fi
  echo "Using IPHLPAPI compatibility shim for XVPN SDK only."
fi
if [[ -n "${XVPN_WINE_DLL_OVERRIDES}" ]]; then
  SDK_ENV+=(WINEDLLOVERRIDES="${XVPN_WINE_DLL_OVERRIDES}")
fi

ASSETS_FOR_SDK="${ASSETS_DIR}"
if command -v winepath >/dev/null 2>&1; then
  converted="$(WINEPREFIX="${WINEPREFIX}" winepath -w "${ASSETS_DIR}" 2>/dev/null || true)"
  if [[ -n "${converted}" ]]; then
    ASSETS_FOR_SDK="${converted}"
  fi
fi

echo "Starting XVPN SDK through Wine on ${BASE} ..."
SDK_ARGS=(-http_addr "127.0.0.1:${SDK_PORT}")
if [[ -n "${XVPN_SDK_PARENT_PROCESS_ID:-}" ]]; then
  SDK_ARGS+=(-parent_process_id "${XVPN_SDK_PARENT_PROCESS_ID}")
fi
(
  cd "${SDK_DIR}"
  env "${SDK_ENV[@]}" "${WINE_BIN}" "${SDK_EXE}" "${SDK_ARGS[@]}"
) >"${RUNTIME_DIR}/xvpnsdk-wine.log" 2>&1 &
SDK_PID=$!

ready=0
for _ in $(seq 1 90); do
  if curl -fsS -X POST -H 'Content-Type: application/json' --data '{}' "${BASE}/api/stat" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.5
done

if [[ "${ready}" != "1" ]]; then
  echo "ERROR: XVPN SDK did not become ready on ${BASE}." >&2
  echo "Last Wine SDK log:" >&2
  tail -80 "${RUNTIME_DIR}/xvpnsdk-wine.log" >&2 || true
  exit 1
fi

echo "XVPN SDK ready."
echo "Public SOCKS5 target: ${PUBLIC_LISTEN}:${PUBLIC_PORT}"
echo "Mode: ${MODE}"
echo "No tun2socks: ${NO_TUN2SOCKS}"

TUN_ARGS=()
if [[ "${NO_TUN2SOCKS}" == "1" ]]; then
  TUN_ARGS+=(--no-tun2socks)
else
  if command -v ip >/dev/null 2>&1 && [[ "$(id -u)" == "0" ]]; then
    ip addr add 172.19.0.1/30 dev lo >/dev/null 2>&1 || true
  fi
fi

export XVPN_DISABLE_UDP

HEALTH_PATH_ARGS=()
if [[ "${HEALTH_VIA_PUBLIC}" == "1" ]]; then
  HEALTH_PATH_ARGS+=(--health-via-public)
fi

DIRECT_FALLBACK_ARGS=()
if [[ "${DIRECT_FALLBACK}" == "1" ]]; then
  DIRECT_FALLBACK_ARGS+=(--direct-fallback)
else
  DIRECT_FALLBACK_ARGS+=(--no-direct-fallback)
fi

"${PYTHON_BIN}" -u "${PROXY_SCRIPT}" \
  --base "${BASE}" \
  --refresh \
  --mode "${MODE}" \
  --assets-dir "${ASSETS_FOR_SDK}" \
  --public-port "${PUBLIC_PORT}" \
  --public-listen "${PUBLIC_LISTEN}" \
  "${HEALTH_PATH_ARGS[@]}" \
  --health-interval "${HEALTH_INTERVAL}" \
  --health-failures "${HEALTH_FAILURES}" \
  --health-probes "${HEALTH_PROBES}" \
  --health-probe-max-failures "${HEALTH_PROBE_MAX_FAILURES}" \
  --health-probe-delay-ms "${HEALTH_PROBE_DELAY_MS}" \
  --public-health-url "${PUBLIC_HEALTH_URL}" \
  --skip-health-when-public-active-seconds "${SKIP_HEALTH_WHEN_PUBLIC_ACTIVE_SECONDS}" \
  --defer-rotate-when-public-active-seconds "${DEFER_ROTATE_WHEN_PUBLIC_ACTIVE_SECONDS}" \
  --max-rotate-defer-seconds "${MAX_ROTATE_DEFER_SECONDS}" \
  --reconnect-delay "${RECONNECT_DELAY}" \
  --start-wait "${START_WAIT}" \
  --stability-probes "${STABILITY_PROBES}" \
  --stability-max-failures "${STABILITY_MAX_FAILURES}" \
  --stability-delay-ms "${STABILITY_DELAY_MS}" \
  --public-max-connections "${PUBLIC_MAX_CONNECTIONS}" \
  --public-upstream-retries "${PUBLIC_UPSTREAM_RETRIES}" \
  --public-stream-retries "${PUBLIC_STREAM_RETRIES}" \
  --public-initial-buffer-bytes "${PUBLIC_INITIAL_BUFFER_BYTES}" \
  --public-relay-buffer-bytes "${PUBLIC_RELAY_BUFFER_BYTES}" \
  --public-client-failover-attempts "${PUBLIC_CLIENT_FAILOVER_ATTEMPTS}" \
  --public-client-failover-wait-seconds "${PUBLIC_CLIENT_FAILOVER_WAIT_SECONDS}" \
  --public-connect-failures-before-rotate "${PUBLIC_CONNECT_FAILURES_BEFORE_ROTATE}" \
  "${DIRECT_FALLBACK_ARGS[@]}" \
  "${TUN_ARGS[@]}" \
  "${EXTRA_ARGS[@]}"
