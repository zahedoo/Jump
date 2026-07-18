#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "core_profile_current.json"
DEFAULT_XRAY = ROOT / "win_proxy_tools" / "xray-v26.3.27" / "xray.exe"
DEFAULT_WORK = ROOT / "WinProxy" / "runtime"


def load_json(path: Path):
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le"):
        try:
            return json.loads(raw.decode(encoding))
        except Exception:
            pass
    return json.loads(raw.decode("utf-8", errors="replace"))


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def nodes_from_profile(profile):
    if isinstance(profile, dict):
        if isinstance(profile.get("nodes"), list):
            return profile["nodes"]
        cso = profile.get("connectorStartOptions")
        if isinstance(cso, dict) and isinstance(cso.get("nodes"), list):
            return cso["nodes"]
    return []


def parse_channels(node):
    env = node.get("coreRuntimeEnvVars") or {}
    raw = env.get("XVPN_PROXY_NODE_CHANNELS") or "[]"
    if isinstance(raw, list):
        channels = raw
    else:
        try:
            channels = json.loads(raw)
        except Exception:
            channels = []
    return [c for c in channels if isinstance(c, dict)]


def infer_purpose(channel):
    attrs = channel.get("nodeAttrs") or {}
    linkline = attrs.get("linkline") or {}
    explicit = (
        channel.get("linePurpose")
        or linkline.get("linePurpose")
        or attrs.get("linePurpose")
        or ""
    )
    explicit = str(explicit).lower()
    if explicit in ("ad", "ads", "advertising"):
        return "ad"
    if explicit in ("normal", "usage"):
        return "normal"
    group_code = str(attrs.get("groupCode") or "")
    sig = "|".join(str(x or "") for x in [
        group_code,
        channel.get("measureUrl"),
        channel.get("nodeId"),
        channel.get("serverId"),
        channel.get("tcpOutboundTag"),
        channel.get("udpOutboundTag"),
    ]).lower()
    return "ad" if group_code.lower().startswith("ad") or "//ad-" in sig or "adirec" in sig else "normal"


def normalize_mode(mode):
    value = str(mode or "").strip().lower().replace("_", "-")
    aliases = {
        "ads": "ad",
        "advertising": "ad",
        "advertisement": "ad",
        "adonly": "ad",
        "ad-only": "ad",
        "raw-ad": "ad",
        "raw-ads": "ad",
        "app": "normal",
        "normal": "normal",
        "smart": "normal",
        "auto": "normal",
    }
    return aliases.get(value, value)


def channel_label(channel):
    attrs = channel.get("nodeAttrs") or {}
    linkline = attrs.get("linkline") or {}
    pieces = []
    for key in ("name", "title", "code", "countryCode", "city", "flag"):
        for src in (linkline, attrs, channel):
            value = src.get(key) if isinstance(src, dict) else None
            if value is not None and str(value).strip():
                pieces.append(str(value).strip())
                break
    seen = []
    for p in pieces:
        if p not in seen:
            seen.append(p)
    return " / ".join(seen[:3]) or str(channel.get("serverAddress") or channel.get("nodeId") or "ad")


def endpoint_from_channel(channel, node):
    host = channel.get("serverAddress")
    port = None
    tag = channel.get("tcpOutboundTag") or channel.get("udpOutboundTag")
    try:
        core = json.loads(node.get("coreConfig") or "{}")
    except Exception:
        core = {}
    for outbound in core.get("outbounds") or []:
        if not isinstance(outbound, dict):
            continue
        if tag and outbound.get("tag") != tag:
            continue
        settings = outbound.get("settings") or {}
        vnext = settings.get("vnext") or []
        if vnext and isinstance(vnext[0], dict):
            host = vnext[0].get("address") or host
            port = vnext[0].get("port") or port
            break
    try:
        port = int(port or channel.get("serverPort") or channel.get("port") or 443)
    except Exception:
        port = 443
    return str(host or ""), port


def tcp_ping(host, port, timeout):
    if not host:
        return None
    start = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return int((time.perf_counter() - start) * 1000)
    except OSError:
        return None


def collect_candidates(profile, timeout, mode):
    mode = normalize_mode(mode)
    out = []
    for node_index, node in enumerate(nodes_from_profile(profile)):
        for channel_index, channel in enumerate(parse_channels(node)):
            purpose = infer_purpose(channel)
            if mode != "all" and purpose != mode:
                continue
            host, port = endpoint_from_channel(channel, node)
            latency = tcp_ping(host, port, timeout)
            out.append({
                "node_index": node_index,
                "channel_index": channel_index,
                "purpose": purpose,
                "node": node,
                "channel": channel,
                "host": host,
                "port": port,
                "latency_ms": latency,
                "label": channel_label(channel),
                "connect_id": str(channel.get("nodeId") or channel.get("serverId") or ""),
                "tag": channel.get("tcpOutboundTag") or channel.get("udpOutboundTag"),
            })
    out.sort(key=lambda c: (c["latency_ms"] is None, c["latency_ms"] if c["latency_ms"] is not None else 10**9, c["node_index"], c["channel_index"]))
    return out


def collect_ad_candidates(profile, timeout):
    return collect_candidates(profile, timeout, "ad")


def purpose_label(candidate):
    return "AD-CONFIG" if candidate.get("purpose") == "ad" else "APP-CONFIG"


def prioritized_profile(profile, candidate):
    copied = json.loads(json.dumps(profile))
    nodes = nodes_from_profile(copied)
    node_index = candidate["node_index"]
    channel_index = candidate["channel_index"]
    if node_index not in range(len(nodes)):
        return copied
    selected = nodes[node_index]
    runtime = selected.get("coreRuntimeEnvVars") or {}
    raw = runtime.get("XVPN_PROXY_NODE_CHANNELS") or "[]"
    try:
        channels = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        channels = []
    if isinstance(channels, list) and channel_index in range(len(channels)):
        reordered_channels = [channels[channel_index]] + [c for i, c in enumerate(channels) if i != channel_index]
        runtime["XVPN_PROXY_NODE_CHANNELS"] = json.dumps(reordered_channels, ensure_ascii=False, separators=(",", ":"))
        selected["coreRuntimeEnvVars"] = runtime
    reordered_nodes = [selected] + [n for i, n in enumerate(nodes) if i != node_index]
    if isinstance(copied, dict) and isinstance(copied.get("nodes"), list):
        copied["nodes"] = reordered_nodes
    else:
        cso = copied.get("connectorStartOptions") if isinstance(copied, dict) else None
        if isinstance(cso, dict) and isinstance(cso.get("nodes"), list):
            cso["nodes"] = reordered_nodes
    return copied


def selected_outbound(node, channel):
    tag = channel.get("tcpOutboundTag") or channel.get("udpOutboundTag")
    core = json.loads(node.get("coreConfig") or "{}")
    for outbound in core.get("outbounds") or []:
        if isinstance(outbound, dict) and outbound.get("tag") == tag:
            copied = json.loads(json.dumps(outbound))
            copied["tag"] = "selected"
            return copied
    raise RuntimeError(f"selected outbound tag not found in coreConfig: {tag}")


def direct_outbound():
    return {"protocol": "freedom", "tag": "direct"}


def block_outbound():
    return {"protocol": "blackhole", "tag": "block"}


def build_xray_config(candidate, socks_port, http_port, socks_listen="127.0.0.1", http_listen="127.0.0.1"):
    node = candidate["node"]
    channel = candidate["channel"]
    base = json.loads(node.get("coreConfig") or "{}")
    config = {}
    for key in ("log", "dns", "policy", "stats", "api", "fakedns", "observatory", "burstObservatory"):
        if key in base:
            config[key] = base[key]
    config["log"] = config.get("log") or {"loglevel": "warning"}
    config["inbounds"] = [
        {
            "tag": "socks-in",
            "listen": str(socks_listen),
            "port": int(socks_port),
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "routeOnly": False},
        },
        {
            "tag": "http-in",
            "listen": str(http_listen),
            "port": int(http_port),
            "protocol": "http",
            "settings": {},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": False},
        },
    ]
    config["outbounds"] = [selected_outbound(node, channel), direct_outbound(), block_outbound()]
    config["routing"] = {
        "domainStrategy": "AsIs",
        "rules": [
            {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
            {"type": "field", "domain": ["geosite:private"], "outboundTag": "direct"},
            {"type": "field", "network": "tcp,udp", "outboundTag": "selected"},
        ],
    }
    return config


def port_open(host, port, timeout=0.25):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def normalize_ip_response(text):
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            raw = str(parsed.get("ip") or parsed.get("query") or parsed.get("origin") or raw).split(",")[0].strip()
    except Exception:
        pass
    parts = raw.split()
    if parts:
        raw = parts[0].strip()
    bits = raw.split(".")
    if len(bits) == 4:
        try:
            nums = [int(x) for x in bits]
            if all(0 <= x <= 255 for x in nums):
                return ".".join(str(x) for x in nums)
        except Exception:
            pass
    return None


def check_public_ip_via_socks(port, host="127.0.0.1"):
    # Uses curl because Windows Python stdlib has no SOCKS client.
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        return None
    urls = ["http://api.ipify.org", "http://icanhazip.com", "http://ifconfig.me/ip"]
    for url in urls:
        try:
            p = subprocess.run(
                [curl, "-sS", "--connect-timeout", "5", "--max-time", "12", "--socks5-hostname", f"{host}:{port}", url],
                capture_output=True,
                text=True,
                timeout=15,
            )
            ip = normalize_ip_response(p.stdout)
            if p.returncode == 0 and ip:
                return ip
        except Exception:
            pass
    return None


def probe_socks(port, host, probes, max_failures, delay=0.7):
    successes = []
    failures = []
    for index in range(max(1, int(probes))):
        ip = check_public_ip_via_socks(port, host)
        if ip:
            successes.append(ip)
        else:
            failures.append(index + 1)
        if index + 1 < probes:
            time.sleep(delay)
    return len(failures) <= max(0, int(max_failures)), (successes[-1] if successes else None), successes, failures


def start_xray(xray, config_path, work_dir):
    env = os.environ.copy()
    env["XRAY_LOCATION_ASSET"] = str(Path(xray).resolve().parent)
    return subprocess.Popen(
        [str(xray), "run", "-config", str(config_path)],
        cwd=str(work_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def main():
    ap = argparse.ArgumentParser(description="JumpJump Windows AD-CONFIG local proxy starter")
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE), help="connector profile JSON; default: core_profile_current.json")
    ap.add_argument("--base", default="http://127.0.0.1:8701")
    ap.add_argument("--refresh", action="store_true", help="fetch fresh live profile through the native SDK API first")
    ap.add_argument("--group-code", default="autonewir")
    ap.add_argument("--refresh-country", default="IR")
    ap.add_argument("--refresh-lang", default="fa")
    ap.add_argument("--ad-media-platform", default="admob")
    ap.add_argument("--xray", default=str(DEFAULT_XRAY), help="path to xray.exe")
    ap.add_argument("--socks-port", type=int, default=10808)
    ap.add_argument("--http-port", type=int, default=10809)
    ap.add_argument("--socks-listen", default="127.0.0.1")
    ap.add_argument("--http-listen", default="127.0.0.1")
    ap.add_argument("--ping-timeout", type=float, default=1.8)
    ap.add_argument("--work-dir", default=str(DEFAULT_WORK))
    ap.add_argument(
        "--mode",
        choices=("ad", "ads", "adonly", "app", "normal", "smart", "all"),
        default="ad",
        help="ad/ads/adonly = raw AD channels; app/normal/smart = normal app channels",
    )
    ap.add_argument("--list-only", action="store_true", help="only print classified channels and ping results")
    ap.add_argument("--write-selected-profile", default="", help="write profile with selected node/channel prioritized")
    ap.add_argument("--stability-probes", type=int, default=3)
    ap.add_argument("--stability-max-failures", type=int, default=0)
    ap.add_argument("--reconnect-delay", type=int, default=2)
    ap.add_argument("--max-generations", type=int, default=0, help="0 means keep fetching fresh live profiles until one works")
    ap.add_argument("--once", action="store_true", help="start, print endpoints, test IP, then stop after --hold seconds")
    ap.add_argument("--hold", type=int, default=0, help="with --once: seconds to keep xray alive after printing")
    args = ap.parse_args()
    args.requested_mode = args.mode
    args.mode = normalize_mode(args.mode)

    profile_path = Path(args.profile).resolve()
    xray = Path(args.xray).resolve()
    work_dir = Path(args.work_dir).resolve()
    if not args.refresh and not profile_path.is_file():
        raise SystemExit(f"profile not found: {profile_path}")
    if not xray.is_file():
        raise SystemExit(f"xray.exe not found: {xray}")

    generation = 0
    while True:
        generation += 1
        if args.refresh:
            from jumpjump_native_proxy import refresh_profile_from_api
            profile = refresh_profile_from_api(
                args.base,
                args.group_code,
                args.refresh_country,
                args.refresh_lang,
                args.ad_media_platform,
            )
        else:
            profile = load_json(profile_path)

        candidates = collect_candidates(profile, args.ping_timeout, args.mode)
        if not candidates:
            print(f"XRAY_FETCH_LIST_FAIL generation={generation} error=no {args.mode} candidates")
            if not args.refresh or (args.max_generations and generation >= args.max_generations):
                raise SystemExit(f"no {args.mode.upper()} channels found in profile")
            time.sleep(max(0, args.reconnect_delay))
            continue

        print(f"XRAY_CANDIDATE_LIST generation={generation} count={len(candidates)} mode={args.mode}")
        for i, c in enumerate(candidates, 1):
            latency = f"{c['latency_ms']}ms" if c["latency_ms"] is not None else "timeout"
            print(f"XRAY_CANDIDATE rank={i} latency={latency} | {purpose_label(c)} | {c['label']} | {c['host']}:{c['port']} | {c['connect_id']} | node={c['node_index']} channel={c['channel_index']}")
        if args.list_only:
            return

        for rank, selected in enumerate(candidates, 1):
            if selected["latency_ms"] is None:
                print(f"XRAY_ATTEMPT_SKIPPED generation={generation} rank={rank} reason=ping_timeout")
                continue
            if args.write_selected_profile:
                selected_profile_path = Path(args.write_selected_profile).resolve()
                save_json(selected_profile_path, prioritized_profile(profile, selected))
                print(f"SELECTED_PROFILE={selected_profile_path}")

            config = build_xray_config(selected, args.socks_port, args.http_port, args.socks_listen, args.http_listen)
            config_path = work_dir / "jumpjump-ad-xray.json"
            save_json(config_path, config)

            if port_open("127.0.0.1", args.socks_port) or port_open("127.0.0.1", args.http_port):
                raise SystemExit(f"local port already in use: socks={args.socks_port} or http={args.http_port}")

            print(f"XRAY_TRY generation={generation} rank={rank} {purpose_label(selected)} id={selected['connect_id']} remote={selected['host']}:{selected['port']} latency={selected['latency_ms']}ms")
            proc = start_xray(xray, config_path, work_dir)
            try:
                started = False
                boot_log = []
                deadline = time.time() + 8
                while time.time() < deadline:
                    if proc.poll() is not None:
                        break
                    if port_open("127.0.0.1", args.socks_port) and port_open("127.0.0.1", args.http_port):
                        started = True
                        break
                    time.sleep(0.2)
                if not started:
                    time.sleep(0.5)
                    if proc.stdout:
                        try:
                            while True:
                                line = proc.stdout.readline()
                                if not line:
                                    break
                                boot_log.append(line.rstrip())
                                if len(boot_log) >= 60:
                                    break
                        except Exception:
                            pass
                    print("XRAY_ATTEMPT_FAILED reason=ports_not_open " + " | ".join(boot_log[-3:]))
                    continue

                ok, ip, successes, failures = probe_socks(
                    args.socks_port,
                    "127.0.0.1",
                    args.stability_probes,
                    args.stability_max_failures,
                )
                if not ok:
                    print(f"XRAY_ATTEMPT_FAILED generation={generation} rank={rank} successes={len(successes)}/{args.stability_probes} failures={len(failures)}")
                    continue

                print(f"XRAY_STARTED generation={generation} rank={rank}")
                print(f"CONNECTED_{purpose_label(selected)}")
                print(f"selected={purpose_label(selected)} {selected['label']} {selected['host']}:{selected['port']} id={selected['connect_id']} latency={selected['latency_ms']}ms")
                print(f"SOCKS5={args.socks_listen}:{args.socks_port}")
                print(f"HTTP={args.http_listen}:{args.http_port}")
                print(f"PUBLIC_IP={ip}")

                if args.once:
                    if args.hold > 0:
                        time.sleep(args.hold)
                    return
                print("Running. Press Ctrl+C to stop.")
                while proc.poll() is None:
                    time.sleep(1)
                print(f"XRAY_EXITED code={proc.returncode}")
            except KeyboardInterrupt:
                print("stopping...")
                return
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()

        print(f"XRAY_CANDIDATE_LIST_EXHAUSTED generation={generation} action=fetch_new_live_api")
        if not args.refresh or (args.max_generations and generation >= args.max_generations):
            raise SystemExit("no working xray proxy after trying candidates")
        time.sleep(max(0, args.reconnect_delay))


if __name__ == "__main__":
    main()
