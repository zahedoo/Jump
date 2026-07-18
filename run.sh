#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

export PUBLIC_PORT="${PUBLIC_PORT:-10880}"
export PUBLIC_LISTEN="${PUBLIC_LISTEN:-0.0.0.0}"
export MODE="${MODE:-ad}"
export HEALTH_INTERVAL="${HEALTH_INTERVAL:-30}"
export HEALTH_FAILURES="${HEALTH_FAILURES:-1}"
export HEALTH_PROBES="${HEALTH_PROBES:-1}"
export HEALTH_PROBE_MAX_FAILURES="${HEALTH_PROBE_MAX_FAILURES:-0}"
export RECONNECT_DELAY="${RECONNECT_DELAY:-3}"
export START_WAIT="${START_WAIT:-45}"
export STABILITY_PROBES="${STABILITY_PROBES:-2}"
export STABILITY_MAX_FAILURES="${STABILITY_MAX_FAILURES:-1}"
export PUBLIC_MAX_CONNECTIONS="${PUBLIC_MAX_CONNECTIONS:-8}"
export PUBLIC_UPSTREAM_RETRIES="${PUBLIC_UPSTREAM_RETRIES:-10}"
export PUBLIC_STREAM_RETRIES="${PUBLIC_STREAM_RETRIES:-3}"
export SKIP_HEALTH_WHEN_PUBLIC_ACTIVE_SECONDS="${SKIP_HEALTH_WHEN_PUBLIC_ACTIVE_SECONDS:-0}"
export XVPN_DISABLE_UDP="${XVPN_DISABLE_UDP:-1}"
export XVPN_WINE_DLL_OVERRIDES="${XVPN_WINE_DLL_OVERRIDES:-iphlpapi,fwpuclnt=n,b}"

if command -v ip >/dev/null 2>&1 && [[ "$(id -u)" == "0" ]]; then
  ip addr add 172.19.0.1/30 dev lo >/dev/null 2>&1 || true
fi

exec bash linux/run_xvpn_wine_proxy.sh --with-tun2socks --with-iphlpapi-shim "$@"

