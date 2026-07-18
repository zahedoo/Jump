#!/usr/bin/env python3
import copy
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8701"
ROOT = Path("/opt/JumpProxyLinuxWine")
RUNTIME = ROOT / "WinProxy" / "runtime"
PAYLOAD_PATH = RUNTIME / "native_start_payload.json"
SOCKS_PORT = 55412


def post(path, payload, timeout=20):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", "replace")
            try:
                return json.loads(body)
            except Exception:
                return {"raw": body}
    except Exception as exc:
        return {"exception": repr(exc)}


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def curl_socks():
    try:
        return subprocess.run(
            [
                "curl",
                "--socks5-hostname",
                f"127.0.0.1:{SOCKS_PORT}",
                "--max-time",
                "5",
                "http://ifconfig.me/ip",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=7,
        ).stdout.strip()
    except Exception as exc:
        return repr(exc)


base_payload = json.loads(PAYLOAD_PATH.read_text())
base_tun = base_payload.get("tun2SocksStartOptions") or {}

variants = [
    ("omit_tun", None, "omit"),
    ("null_tun", None, "null"),
    ("empty_object", {}, "set"),
    ("socks_only", {"socksPort": SOCKS_PORT}, "set"),
    ("dns_empty_list", {**base_tun, "dnsServers": []}, "set"),
    ("dns_empty_string", {**base_tun, "dnsServers": "", "dnsServer": "", "dns": "", "dns_servers": ""}, "set"),
    ("dns_null", {**base_tun, "dnsServers": None, "dnsServer": None, "dns": None, "dns_servers": None}, "set"),
    ("no_auto_route", {**base_tun, "autoRoute": False, "strictRoute": False, "auto_route": False, "strict_route": False}, "set"),
    (
        "no_dns_no_route",
        {
            **base_tun,
            "dnsServers": [],
            "dnsServer": "",
            "dns": "",
            "dns_servers": "",
            "enableDns": False,
            "setDns": False,
            "dnsEnabled": False,
            "autoRoute": False,
            "strictRoute": False,
            "auto_route": False,
            "strict_route": False,
        },
        "set",
    ),
    ("no_ips", {**base_tun, "tunIps": []}, "set"),
    ("empty_name", {**base_tun, "tunName": ""}, "set"),
    ("disabled_flags", {**base_tun, "enabled": False, "enable": False, "disabled": True}, "set"),
    ("base_tun", base_tun, "set"),
]

for name, tun_value, action in variants:
    post("/api/proxy_connector_stop", {}, timeout=8)
    time.sleep(0.2)
    payload = copy.deepcopy(base_payload)
    if action == "omit":
        payload.pop("tun2SocksStartOptions", None)
    elif action == "null":
        payload["tun2SocksStartOptions"] = None
    else:
        payload["tun2SocksStartOptions"] = tun_value

    started = post("/api/proxy_connector_start", payload, timeout=45)
    time.sleep(0.6)
    opened = port_open(SOCKS_PORT)
    print(f"VARIANT={name} RESPONSE={json.dumps(started, ensure_ascii=False)[:500]} PORT_OPEN={opened}")
    if opened:
        print(f"VARIANT={name} CURL={curl_socks()}")
    post("/api/proxy_connector_stop", {}, timeout=8)
