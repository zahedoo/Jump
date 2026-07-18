#!/usr/bin/env bash
set -Eeuo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-10880}"
URL="${3:-http://ifconfig.me/ip}"

echo "Testing SOCKS5 ${HOST}:${PORT} -> ${URL}"
curl -v \
  --connect-timeout 8 \
  --max-time 20 \
  --socks5-hostname "${HOST}:${PORT}" \
  "${URL}"
echo

