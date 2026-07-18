#!/usr/bin/env python3
import argparse
import ipaddress
import select
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

def app_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT = app_root()
RUNTIME = ROOT / "WinProxy" / "runtime"
DEFAULT_BASE = "http://127.0.0.1:6676"
DEFAULT_PROFILE = RUNTIME / "windows_native_ad_prioritized_profile.json"
DEFAULT_ASSETS = ROOT / "win_jump_install" / "bin" / "assets"
DEFAULT_DEBUG_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0 Herring/95.1.1930.31"
)
DEFAULT_API_CONFIG = {
    "startId": "1783759500718",
    "success": True,
    "apiGroupUrls": {
        "xapi": [
            "https://tafox.gokarel.xyz",
            "https://gayosu.riponex.my",
            "https://qeyoxohu.fumatek.baby",
            "https://d2rmfl6fj3mcoq.cloudfront.net",
            "https://cukuju.kemoriv.my",
            "https://livisiq.fonarex.my",
            "https://zuhubef.darikon.my",
            "https://zogoway.jomalex.baby",
        ],
        "xlog": [
            "https://apilog.e18api2ed5ns9xh5a.xyz:2096",
            "https://apilog2.e18api2ed5ns9xh5a.xyz:2096",
            "https://d1zsg7hlv93cca.cloudfront.net",
            "https://d3w0jzdrix74az.cloudfront.net",
            "https://d2qw3kr6rbkb4.cloudfront.net",
            "https://d3ovjq9yyr3gvv.cloudfront.net",
            "https://d2u0czku5lzf0d.cloudfront.net",
            "https://d1215j61egvsq3.cloudfront.net",
        ],
        "xrouter": [
            "https://d2z5e7lt7ltwz.cloudfront.net",
            "https://d3ooqmk6zzjzwp.cloudfront.net",
            "https://d15zz1wnshx5hy.cloudfront.net",
            "https://dbh3kkydtv72p.cloudfront.net",
            "https://d17jrd0izycd8u.cloudfront.net",
            "https://cfn5qwc4.trilqavo.forum",
            "https://d36eci12znttta.cloudfront.net",
            "https://d3cih9w5t9kofz.cloudfront.net",
        ],
    },
    "fallbackSuccess": False,
    "fallbackApiGroupUrls": None,
    "initApiUrlsCheckTimeout": 3743,
    "newApiUrlsCheckTimeout": 0,
    "apiConfigLoadTimeout": 0,
    "apiConfigLoadUrl": None,
    "apiConfigLoadUrlSource": None,
    "apiConfigApiGroupUrls": None,
    "apiConfigHttpRespData": None,
    "timeout": 3743,
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def timestamp_id():
    return time.strftime("%Y%m%d-%H%M%S") + f"-{int((time.time() % 1) * 1000):03d}"


def post(base, path, body, timeout=40):
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = Request(base + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def sdk_stat_ok(base, timeout=5):
    try:
        post(base, "/api/stat", {}, timeout=timeout)
        return True
    except Exception:
        return False


def call_sdk_api(base, api_group, sub_path, body, compression=False, timeout=25):
    request = {
        "apiGroup": api_group,
        "timeout": timeout,
        "callId": str(int(time.time() * 1000)),
        "bodyContent": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        "maxRetryCount": 4,
        "callInterval": 0,
        "httpResponseChecker": {
            "statusCodes": ["200"],
            "headers": {"Content-Type": ["application/json"], "X-Nl-Response-Signature": []},
        },
        "httpResponseErrorCodeJqPath": "errorCode",
        "httpResponseErrorMessageJqPath": "errorMessage",
        "bodyCompression": bool(compression),
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "urlSubPath": sub_path,
        "domainResolveDns": ["8.8.8.8", "localhost"],
    }
    outer = post(base, "/api/api_service_call_api", request, timeout=timeout + 12)
    response = (outer.get("data") or {}).get("response") or {}
    raw = response.get("bodyContent") or ""
    try:
        return json.loads(raw)
    except Exception:
        return {"success": False, "errorMessage": "non-json response", "raw": raw[:500]}


def find_profile(value):
    if isinstance(value, dict):
        if isinstance(value.get("nodes"), list) and value.get("nodes"):
            return value
        for child in value.values():
            found = find_profile(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_profile(child)
            if found is not None:
                return found
    return None


def load_prefs():
    prefs_path = Path(os.environ.get("APPDATA", "")) / "app.jumpjumpvpn" / "jumpjumpvpn" / "shared_preferences.json"
    if prefs_path.exists():
        return json.loads(prefs_path.read_text(encoding="utf-8"))

    device_path = RUNTIME / "server_device_id.txt"
    device_path.parent.mkdir(parents=True, exist_ok=True)
    if device_path.exists():
        device_id = device_path.read_text(encoding="utf-8").strip()
    else:
        device_id = uuid.uuid4().hex
        device_path.write_text(device_id, encoding="utf-8")

    print(f"PREFS_FALLBACK=embedded deviceId={device_id}")
    return {
        "flutter.apiGroupConfig": json.dumps(DEFAULT_API_CONFIG, ensure_ascii=False, separators=(",", ":")),
        "flutter.deviceId": device_id,
        "flutter.debugUserAgent": DEFAULT_DEBUG_USER_AGENT,
        "flutter.groupInfos": [
            json.dumps(
                {
                    "favorite": False,
                    "useCount": 0,
                    "group": {
                        "id": "embedded-autonewir",
                        "name": "Auto Location",
                        "code": "autonewir",
                        "param": "{\"g\":\"autonewir\",\"adInterstitialUnbounded\":false}",
                        "flag": "default",
                        "country": "Default",
                        "memberLevel": 0,
                        "sort": 8010,
                        "nodes": [],
                        "tags": [],
                        "congestion": "low",
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        ],
    }


def group_from_list(groups, group_code):
    if group_code:
        for group in groups:
            if group.get("code") == group_code:
                return group
    for group in groups:
        if "auto" in str(group.get("code") or "").lower():
            return group
    if groups:
        return groups[0]
    return None


def group_from_prefs(prefs, group_code):
    for raw in prefs.get("flutter.groupInfos") or []:
        try:
            parsed = json.loads(raw)
            group = parsed.get("group") or parsed
        except Exception:
            continue
        if group_code and group.get("code") == group_code:
            return group
    for raw in prefs.get("flutter.groupInfos") or []:
        try:
            parsed = json.loads(raw)
            group = parsed.get("group") or parsed
        except Exception:
            continue
        if "auto" in str(group.get("code") or "").lower():
            return group
    raise RuntimeError("no usable group found in shared preferences")


def count_ad_channels(profile):
    count = 0
    for node in nodes(profile):
        for channel in channels(node):
            if purpose(channel) == "ad":
                count += 1
    return count


def normalize_mode(mode):
    value = str(mode or "").strip().lower().replace("_", "-")
    aliases = {
        "ads": "ad",
        "advertising": "ad",
        "advertisement": "ad",
        "ad-only": "adonly",
        "raw-ad": "adonly",
        "raw-ads": "adonly",
        "normal": "app",
        "smart": "app",
        "auto": "app",
        "application": "app",
    }
    return aliases.get(value, value)


def refresh_profile_from_api(base, group_code, refresh_country, refresh_lang, ad_media_platform):
    prefs = load_prefs()
    api_config = json.loads(prefs["flutter.apiGroupConfig"])
    device_id = prefs["flutter.deviceId"]
    post(base, "/api/api_service_update_config", api_config, timeout=20)
    ua = prefs.get("flutter.debugUserAgent")
    if ua:
        try:
            post(base, "/api/set_global_http_headers", {"User-Agent": ua}, timeout=10)
        except Exception:
            pass

    common = {
        "productId": 10001,
        "platform": "mobile-android",
        "channel": "google",
        "appVer": 320,
        "ver": 320,
        "lang": refresh_lang,
        "version": "3.2.0",
        "versionName": "3.2.0",
        "appVersion": "3.2.0",
        "buildNumber": 320,
        "deviceid": device_id,
        "deviceId": device_id,
        "authorization": "",
        "deviceModel": "SM-G988N",
        "deviceOs": "13",
        "adMediaPlatform": ad_media_platform,
        "useOtherVpn": False,
        "deviceInfoV2": {
            "languageCode": refresh_lang,
            "countryCode": refresh_country,
            "timezone": "UTC+3",
            "simCountryCode": refresh_country,
            "networkCountryCode": refresh_country,
            "timezoneCountry": "Asia/Tehran" if refresh_country.upper() == "IR" else refresh_country,
        },
        "routerUserGeo": {"deviceid": device_id, "countryCode": refresh_country},
        "fingerprintRawDatas": {
            "keychain": "",
            "googleID": "",
            "gsfID": "",
            "mediaID": "",
            "androidID": device_id,
        },
    }
    guest = call_sdk_api(base, "xapi", "/api/v1.0/guestLogin", common, compression=True, timeout=20)
    auth = (((guest.get("data") or {}).get("userConfig") or {}).get("authorization") or "")
    if not auth:
        raise RuntimeError("fresh guest login did not return authorization")

    response_groups = ((((guest.get("data") or {}).get("groups") or {}).get("normal") or {}).get("list") or [])
    group = group_from_list(response_groups, group_code)
    if group is None:
        group = group_from_prefs(prefs, group_code)
    legacy = {
        "productId": 10001,
        "platform": "mobile-android",
        "channel": "google",
        "appVer": 312,
        "lang": refresh_lang,
        "deviceId": device_id,
        "deviceModel": "SM-G988N",
        "deviceOs": "13",
        "authorization": auth,
        "groupParam": group.get("param") or "",
        "fetchCount": 4,
        "clientConfig": {
            "platformOs": "android",
            "logLevel": "none",
            "inboundsSocksPort": 55412,
            "routingMode": "global",
            "routingCountryCode": refresh_country.lower(),
            "sniffingDomainsExcluded": [],
            "outboundsByedpiSocksPort": 55413,
            "outboundsDnsttPorts": [55414, 55415],
        },
        "useOtherVpn": False,
        "deviceInfoV2": common["deviceInfoV2"],
    }
    response = call_sdk_api(base, "xrouter", "/api/v1.0/getNodesV2", legacy, compression=False, timeout=30)
    profile = find_profile(response)
    if not profile:
        raise RuntimeError("fresh getNodesV2 returned no profile: " + str(response.get("errorMessage") or response)[:300])
    out = RUNTIME / "windows_native_fresh_profile.json"
    archive = RUNTIME / "api_profiles" / f"fresh_profile_{timestamp_id()}.json"
    save_json(out, profile)
    save_json(archive, profile)
    print("CONFIG_SOURCE=live_api")
    print(f"FRESH_PROFILE={out}")
    print(f"FRESH_PROFILE_ARCHIVE={archive}")
    print(f"FRESH_GROUP={group.get('code')}")
    print(f"FRESH_COUNTRY={refresh_country}")
    print(f"FRESH_LANG={refresh_lang}")
    print(f"FRESH_AD_MEDIA={ad_media_platform}")
    print(f"FRESH_AD_CHANNELS={count_ad_channels(profile)}")
    return profile


def nodes(profile):
    if isinstance(profile.get("nodes"), list):
        return profile["nodes"]
    cso = profile.get("connectorStartOptions")
    if isinstance(cso, dict) and isinstance(cso.get("nodes"), list):
        return cso["nodes"]
    return []


def channels(node):
    raw = (node.get("coreRuntimeEnvVars") or {}).get("XVPN_PROXY_NODE_CHANNELS") or "[]"
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        parsed = []
    return [c for c in parsed if isinstance(c, dict)]


def purpose(channel):
    attrs = channel.get("nodeAttrs") or {}
    linkline = attrs.get("linkline") or {}
    explicit = str(channel.get("linePurpose") or linkline.get("linePurpose") or attrs.get("linePurpose") or "").lower()
    sig = "|".join(str(x or "") for x in [explicit, attrs.get("groupCode"), channel.get("measureUrl")]).lower()
    if explicit in {"ad", "ads", "advertising"} or "adirec" in sig or "//ad-" in sig:
        return "ad"
    return "app"


def endpoint(node, channel):
    tag = channel.get("tcpOutboundTag") or channel.get("udpOutboundTag")
    host = channel.get("serverAddress") or ""
    port = 443
    try:
        core = json.loads(node.get("coreConfig") or "{}")
        for outbound in core.get("outbounds") or []:
            if tag and outbound.get("tag") != tag:
                continue
            vnext = ((outbound.get("settings") or {}).get("vnext") or [{}])[0]
            host = vnext.get("address") or host
            port = int(vnext.get("port") or port)
            break
    except Exception:
        pass
    return host, port


def tcp_ping(host, port, timeout):
    start = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return int((time.perf_counter() - start) * 1000)
    except OSError:
        return None


_REAL_PING_CACHE = {}
_HTTP_MEASURE_CACHE = {}


def resolve_ipv4(host):
    try:
        ipaddress.ip_address(str(host))
        return str(host)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(str(host), None, socket.AF_INET, socket.SOCK_STREAM)
        for info in infos:
            ip = info[4][0]
            if ip:
                return ip
    except OSError:
        return ""
    return ""


def real_ping(host, timeout, count=2):
    """Measure real ICMP ping to the resolved IPv4 address.

    TCP connect latency only proves the port accepted a socket. ICMP ping is
    reported separately so the UI can distinguish port reachability from actual
    network latency. Some providers block ICMP; in that case the IP is still
    returned and ping_ms is None.
    """
    timeout_ms = max(300, int(float(timeout) * 1000))
    ip = resolve_ipv4(host)
    if not ip:
        return "", None

    key = (ip, timeout_ms, int(count))
    if key in _REAL_PING_CACHE:
        return _REAL_PING_CACHE[key]

    try:
        p = subprocess.run(
            ["ping.exe", "-4", "-n", str(int(count)), "-w", str(timeout_ms), ip],
            capture_output=True,
            text=True,
            timeout=max(3, int(count) * (timeout_ms / 1000.0 + 1.0)),
        )
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        values = [
            int(x)
            for x in re.findall(r"(?:time|زمان)\s*[=<]\s*(\d+)\s*ms", out, flags=re.IGNORECASE)
        ]
        if values:
            result = (ip, int(sum(values) / len(values)))
        else:
            avg = re.search(r"(?:Average|Avg|میانگین)\s*=\s*(?:<)?(\d+)\s*ms", out, flags=re.IGNORECASE)
            result = (ip, int(avg.group(1)) if avg else None)
    except Exception:
        result = (ip, None)
    _REAL_PING_CACHE[key] = result
    return result


def http_measure_ping(url, timeout):
    if not url:
        return "", None
    key = (str(url), max(300, int(float(timeout) * 1000)))
    if key in _HTTP_MEASURE_CACHE:
        return _HTTP_MEASURE_CACHE[key]
    try:
        parsed = urlparse(str(url))
        ip = resolve_ipv4(parsed.hostname or "")
        req = Request(str(url), headers={"User-Agent": DEFAULT_DEBUG_USER_AGENT})
        start = time.perf_counter()
        with urlopen(req, timeout=max(0.5, float(timeout))) as resp:
            resp.read(64)
        result = (ip, int((time.perf_counter() - start) * 1000))
    except Exception:
        result = ("", None)
    _HTTP_MEASURE_CACHE[key] = result
    return result


def endpoint_metrics(host, port, timeout, channel=None):
    tcp = tcp_ping(host, port, timeout)
    ip, icmp = real_ping(host, timeout)
    ping_ip = ip
    real_value = icmp
    real_source = "ICMP" if icmp is not None else ""
    if real_value is None:
        measure_ip, http_value = http_measure_ping((channel or {}).get("measureUrl"), timeout)
        if http_value is not None:
            ping_ip = measure_ip or ping_ip
            real_value = http_value
            real_source = "HTTP"
    return {
        "host": host,
        "port": port,
        "latency_ms": tcp,
        "ip": ip,
        "ping_ip": ping_ip,
        "real_ping_ms": real_value,
        "real_ping_source": real_source or "NONE",
    }


def candidate_priority(candidate):
    purpose_value = candidate.get("purpose")
    if purpose_value == "adpair":
        return 0
    if purpose_value in ("app", "normal") and candidate.get("ad_id"):
        return 1
    if purpose_value in ("app", "normal"):
        return 2
    if purpose_value == "ad":
        return 3
    return 9


def candidate_sort_key(candidate):
    real = candidate.get("real_ping_ms")
    tcp = candidate.get("latency_ms")
    return (
        candidate_priority(candidate),
        real is None,
        real if real is not None else 10**9,
        tcp is None,
        tcp if tcp is not None else 10**9,
    )


def channel_identity(node, channel):
    return str(channel.get("nodeId") or channel.get("serverId") or node.get("nodeId") or node.get("id") or "")


def ad_pair_candidates(profile, timeout):
    out = []
    seen = set()
    for ni, node in enumerate(nodes(profile)):
        chs = channels(node)
        normal_channels = [(ci, ch) for ci, ch in enumerate(chs) if purpose(ch) != "ad"]
        ad_channels = [(ci, ch) for ci, ch in enumerate(chs) if purpose(ch) == "ad"]
        if not normal_channels or not ad_channels:
            continue

        ranked_ads = []
        for ai, ad_ch in ad_channels:
            ad_host, ad_port = endpoint(node, ad_ch)
            ad_metrics = endpoint_metrics(ad_host, ad_port, timeout, ad_ch)
            ranked_ads.append((ad_metrics, ai, ad_ch, ad_host, ad_port))
        ranked_ads.sort(
            key=lambda x: (
                x[0]["real_ping_ms"] is None,
                x[0]["real_ping_ms"] if x[0]["real_ping_ms"] is not None else 10**9,
                x[0]["latency_ms"] is None,
                x[0]["latency_ms"] if x[0]["latency_ms"] is not None else 10**9,
            )
        )
        ad_metrics, ad_index, ad_channel, ad_host, ad_port = ranked_ads[0]

        for ci, channel in normal_channels:
            host, port = endpoint(node, channel)
            metrics = endpoint_metrics(host, port, timeout, channel)
            normal_id = channel_identity(node, channel)
            ad_id = channel_identity(node, ad_channel)
            item = {
                "node_index": ni,
                "channel_index": ci,
                "ad_channel_index": ad_index,
                "channel_order": [ci, ad_index],
                "purpose": "adpair",
                "node": node,
                "channel": channel,
                "ad_channel": ad_channel,
                "host": host,
                "port": port,
                "latency_ms": metrics["latency_ms"],
                "ip": metrics["ip"],
                "ping_ip": metrics["ping_ip"],
                "real_ping_ms": metrics["real_ping_ms"],
                "real_ping_source": metrics["real_ping_source"],
                "id": f"{normal_id}+{ad_id}",
                "normal_id": normal_id,
                "ad_id": ad_id,
                "ad_host": ad_host,
                "ad_port": ad_port,
                "ad_latency_ms": ad_metrics["latency_ms"],
                "ad_ip": ad_metrics["ip"],
                "ad_ping_ip": ad_metrics["ping_ip"],
                "ad_real_ping_ms": ad_metrics["real_ping_ms"],
                "ad_real_ping_source": ad_metrics["real_ping_source"],
            }
            key = candidate_key(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    out.sort(key=candidate_sort_key)
    return out


def raw_channel_candidates(profile, mode, timeout):
    out = []
    seen = set()
    for ni, node in enumerate(nodes(profile)):
        chs = channels(node)
        ranked_ads = []
        for ai, ad_ch in enumerate(chs):
            if purpose(ad_ch) != "ad":
                continue
            ad_host, ad_port = endpoint(node, ad_ch)
            ad_metrics = endpoint_metrics(ad_host, ad_port, timeout, ad_ch)
            ranked_ads.append((ad_metrics, ai, ad_ch, ad_host, ad_port))
        ranked_ads.sort(
            key=lambda x: (
                x[0]["real_ping_ms"] is None,
                x[0]["real_ping_ms"] if x[0]["real_ping_ms"] is not None else 10**9,
                x[0]["latency_ms"] is None,
                x[0]["latency_ms"] if x[0]["latency_ms"] is not None else 10**9,
            )
        )
        best_ad = ranked_ads[0] if ranked_ads else None

        for ci, channel in enumerate(chs):
            p = purpose(channel)
            if mode != "all" and p != mode:
                continue
            host, port = endpoint(node, channel)
            metrics = endpoint_metrics(host, port, timeout, channel)
            item = {
                "node_index": ni,
                "channel_index": ci,
                "purpose": p,
                "node": node,
                "channel": channel,
                "host": host,
                "port": port,
                "latency_ms": metrics["latency_ms"],
                "ip": metrics["ip"],
                "ping_ip": metrics["ping_ip"],
                "real_ping_ms": metrics["real_ping_ms"],
                "real_ping_source": metrics["real_ping_source"],
                "id": channel_identity(node, channel),
            }
            if p == "app" and best_ad is not None:
                ad_metrics, ad_index, ad_channel, ad_host, ad_port = best_ad
                item.update(
                    {
                        "ad_channel_index": ad_index,
                        "channel_order": [ci, ad_index],
                        "ad_channel": ad_channel,
                        "normal_id": channel_identity(node, channel),
                        "ad_id": channel_identity(node, ad_channel),
                        "ad_host": ad_host,
                        "ad_port": ad_port,
                        "ad_latency_ms": ad_metrics["latency_ms"],
                        "ad_ip": ad_metrics["ip"],
                        "ad_ping_ip": ad_metrics["ping_ip"],
                        "ad_real_ping_ms": ad_metrics["real_ping_ms"],
                        "ad_real_ping_source": ad_metrics["real_ping_source"],
                    }
                )
            key = candidate_key(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    out.sort(key=candidate_sort_key)
    return out


def candidates(profile, mode, timeout):
    mode = normalize_mode(mode)
    if mode == "ad":
        # Default AD mode is robust: prefer Android-like normal+AD pairs,
        # then fall back to raw AD channels from the same fresh API list.
        # Some live API responses contain only raw AD channels, so pair-only
        # selection can incorrectly report "no ad candidates found".
        return ad_pair_candidates(profile, timeout) + raw_channel_candidates(profile, "ad", timeout)
    if mode == "adonly":
        return raw_channel_candidates(profile, "ad", timeout)
    return raw_channel_candidates(profile, mode, timeout)


def candidate_key(candidate):
    return "|".join(
        str(candidate.get(k) or "")
        for k in ("purpose", "id", "host", "port", "ad_id")
    )


def prioritize(profile, selected):
    copied = json.loads(json.dumps(profile))
    ns = nodes(copied)
    ni = selected["node_index"]
    ci = selected["channel_index"]
    selected_node = ns[ni]
    runtime = selected_node.get("coreRuntimeEnvVars") or {}
    chs = channels(selected_node)
    ordered_indices = []
    for idx in selected.get("channel_order") or [ci]:
        if isinstance(idx, int) and idx in range(len(chs)) and idx not in ordered_indices:
            ordered_indices.append(idx)
    if ordered_indices:
        runtime["XVPN_PROXY_NODE_CHANNELS"] = json.dumps(
            [chs[i] for i in ordered_indices] + [c for i, c in enumerate(chs) if i not in ordered_indices],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        selected_node["coreRuntimeEnvVars"] = runtime
    reordered = [selected_node] + [n for i, n in enumerate(ns) if i != ni]
    if isinstance(copied.get("nodes"), list):
        copied["nodes"] = reordered
    elif isinstance(copied.get("connectorStartOptions"), dict):
        copied["connectorStartOptions"]["nodes"] = reordered
    return copied


def inbound_socks_port(profile):
    first = nodes(profile)[0]
    core = json.loads(first.get("coreConfig") or "{}")
    for inbound in core.get("inbounds") or []:
        if inbound.get("protocol") == "socks":
            return int(inbound.get("port"))
    raise RuntimeError("no socks inbound found in selected coreConfig")


def linux_wine_core_config(core_config):
    raw = core_config or ""
    if not raw:
        return raw
    disable_udp = os.name != "nt" or os.environ.get("XVPN_DISABLE_UDP", "").strip() == "1"
    if not disable_udp:
        return raw
    try:
        core = json.loads(raw)
    except Exception:
        return raw
    changed = False
    for inbound in core.get("inbounds") or []:
        if inbound.get("protocol") == "socks":
            settings = inbound.setdefault("settings", {})
            if settings.get("udp") is not False:
                settings["udp"] = False
                changed = True
            sniffing = inbound.get("sniffing")
            if isinstance(sniffing, dict):
                dest = sniffing.get("destOverride")
                if isinstance(dest, list) and "quic" in dest:
                    sniffing["destOverride"] = [x for x in dest if x != "quic"]
                    changed = True
    return json.dumps(core, ensure_ascii=False, separators=(",", ":")) if changed else raw


def min_node(node):
    return {
        "nodeId": str(node.get("nodeId") or node.get("id") or ""),
        "coreConfig": linux_wine_core_config(node.get("coreConfig") or ""),
        "coreType": node.get("coreType") or "xray",
        "coreRuntimeEnvVars": node.get("coreRuntimeEnvVars") or {},
    }


def sdk_assets_path(assets_dir):
    raw = str(assets_dir or "").strip()
    if re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith("\\\\"):
        return raw
    return str(Path(raw).resolve())


def build_start_payload(profile, assets_dir, skip_measure, no_tun2socks=False):
    ns = [min_node(n) for n in nodes(profile)]
    first = ns[0]
    socks_port = inbound_socks_port(profile)
    payload = {
        "startId": "native-" + str(int(time.time() * 1000)),
        "assetsDir": sdk_assets_path(assets_dir),
        "proxyServiceStartOptions": {
            "usePlatformAutoDetectInterfaceControl": False,
            "networkStatusDetect": {
                "interval": 10,
                "checkUrls": [
                    "https://connectivitycheck.gstatic.com/generate_204",
                    "http://www.msftncsi.com/ncsi.txt",
                    "https://connectivitycheck.android.com/generate_204",
                    "http://www.msftconnecttest.com/connecttest.txt",
                ],
            },
            "coreConfig": first["coreConfig"],
            "coreType": first["coreType"],
            "coreRuntimeEnvVars": first["coreRuntimeEnvVars"],
            "deviceIp": "",
            "localDnsServer": "",
            "memoryLimit": 0,
            "memoryLimitGo": 0,
            "metricsEnabled": True,
        },
        "proxyServiceMeasureOptions": {"timeout": 4, "times": 1, "disableParallel": False},
        "nodes": ns,
        "maxRetryCount": 1,
        "skipMeasure": bool(skip_measure),
    }
    if not no_tun2socks:
        payload["tun2SocksStartOptions"] = {
            "tunName": "JumpJumpTun",
            "tunIps": ["172.19.0.1/30"],
            "socksPort": socks_port,
            "logLevel": "error",
            "allowedProcessList": [],
            "disallowedProcessList": [],
        }
    return socks_port, payload


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.4):
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
            for key in ("ip", "query", "origin"):
                if key in parsed:
                    ip = normalize_ip_response(str(parsed[key]).split(",")[0])
                    if ip:
                        return ip
    except Exception:
        pass

    candidates = [raw]
    candidates += re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", raw)
    candidates += re.findall(r"(?i)(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}", raw)
    for candidate in candidates:
        candidate = candidate.strip().strip("[](){}<>,;\"'")
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return None


def curl_ip(port, socks_host="127.0.0.1"):
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        return None, "curl not found", ""
    errors = []
    # Keep api.ipify last. Some AD routes return an empty response for ipify
    # and, worse, can make the native connector drop the local SOCKS listener.
    # ifconfig/icanhazip have been more stable for these AD configs.
    urls = [
        "https://icanhazip.com",
        "http://icanhazip.com",
        "https://ifconfig.me/ip",
        "http://ifconfig.me/ip",
        "http://api.ipify.org?format=json",
        "https://api.ipify.org?format=json",
    ]
    for url in urls:
        args = [curl, "-sS", "--connect-timeout", "4", "--max-time", "8", "--socks5-hostname", f"{socks_host}:{port}"]
        if url.startswith("https://"):
            args.append("--insecure")
        args.append(url)
        p = subprocess.run(args, capture_output=True, text=True, timeout=20)
        out = p.stdout.strip()
        ip = normalize_ip_response(out)
        if p.returncode == 0 and ip:
            return ip, "", url
        if p.returncode == 0 and out:
            errors.append(f"{url}: invalid ip response {out[:120]!r}")
            continue
        errors.append(f"{url}: {p.stderr.strip() or ('exit ' + str(p.returncode))}")
        if socks_host in {"127.0.0.1", "localhost"} and not port_open(port):
            errors.append(f"{url}: local socks listener {socks_host}:{port} closed during health check")
            break
    return None, " | ".join(errors), ""


PROBE_URLS = [
    "http://api.ipify.org",
    "http://icanhazip.com",
    "http://ifconfig.me/ip",
]


def curl_single_ip(port, socks_host, url):
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        return None, "curl not found", url
    args = [curl, "-sS", "--connect-timeout", "5", "--max-time", "12", "--socks5-hostname", f"{socks_host}:{port}"]
    if url.startswith("https://"):
        args.append("--insecure")
    args.append(url)
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=18)
    except Exception as exc:
        return None, str(exc), url
    out = p.stdout.strip()
    ip = normalize_ip_response(out)
    if p.returncode == 0 and ip:
        return ip, "", url
    if p.returncode == 0 and out:
        return None, f"invalid ip response {out[:120]!r}", url
    return None, p.stderr.strip() or ("exit " + str(p.returncode)), url


AUTO_IPINFO_URLS = [
    "https://icanhazip.com",
    "http://icanhazip.com",
    "https://ifconfig.me/ip",
    "http://ifconfig.me/ip",
    "http://api.ipify.org?format=json",
    "https://api.ipify.org?format=json",
]


BLOCK_HTTP_STATUSES = {400, 401, 403, 407, 429, 451}


def load_telegram_config():
    config = {
        "enabled": True,
        "botToken": os.environ.get("JUMP_TELEGRAM_BOT_TOKEN", "").strip(),
        "chatId": os.environ.get("JUMP_TELEGRAM_CHAT_ID", "").strip(),
    }
    config_path = ROOT / "telegram_config.json"
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            config["enabled"] = bool(data.get("enabled", True))
            config["botToken"] = str(data.get("botToken") or data.get("token") or config["botToken"] or "").strip()
            config["chatId"] = str(
                data.get("chatId") or data.get("chat_id") or data.get("userId") or config["chatId"] or ""
            ).strip()
        except Exception as exc:
            print(f"TELEGRAM_CONFIG_IGNORED={exc}", flush=True)
    config["enabled"] = bool(config.get("enabled") and config.get("botToken") and config.get("chatId"))
    return config


def send_telegram(config, text):
    if not config or not config.get("enabled"):
        return False
    payload = urlencode(
        {
            "chat_id": config["chatId"],
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{config['botToken']}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    first_error = ""
    try:
        with urlopen(req, timeout=12) as resp:
            resp.read()
        print("TELEGRAM_SENT=true", flush=True)
        return True
    except Exception as exc:
        first_error = str(exc)

    curl = shutil.which("curl")
    if curl:
        try:
            proc = subprocess.run(
                [
                    curl,
                    "-sS",
                    "--max-time",
                    "15",
                    "-X",
                    "POST",
                    f"https://api.telegram.org/bot{config['botToken']}/sendMessage",
                    "-d",
                    f"chat_id={config['chatId']}",
                    "-d",
                    "disable_web_page_preview=true",
                    "--data-urlencode",
                    f"text={text}",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode == 0 and '"ok":true' in (proc.stdout or ""):
                print("TELEGRAM_SENT=true", flush=True)
                return True
            fallback_error = (proc.stderr or proc.stdout or "").strip()[:240]
        except Exception as exc:
            fallback_error = str(exc)
    else:
        fallback_error = "curl not found"

    print(f"TELEGRAM_SENT=false urllib={first_error[:160]} curl={fallback_error}", flush=True)
    return False


def compact_status_text(text, limit=900):
    one_line = re.sub(r"\s+", " ", str(text or "")).strip()
    one_line = re.sub(
        r"curl: \(7\) Failed to connect to 127\.0\.0\.1 port \d+ after \d+ ms: Could not connect to server",
        "local_socks_closed",
        one_line,
    )
    one_line = re.sub(r"curl: \(28\)[^|]+", "timeout", one_line)
    one_line = one_line.replace("curl: (52) Empty reply from server", "empty_reply")
    one_line = one_line.replace("cannot complete SOCKS5 connection", "socks5_connect_failed")
    return one_line[:limit]


def notify_no_proxy(config, reason, generation, mode, reconnects):
    send_telegram(
        config,
        "JumpProxy Auto\n"
        "وضعیت: پروکسی خروجی سالم پیدا نشد.\n"
        "عملیات: refresh و تست تک‌به‌تک ادامه دارد.\n"
        f"mode={mode} generation={generation} reconnects={reconnects}\n"
        f"reason={compact_status_text(reason)}",
    )


def notify_proxy_found(config, selected, result, generation, rank, public_port):
    send_telegram(
        config,
        "JumpProxy Auto\n"
        "وضعیت: پروکسی خروجی پیدا شد و اتصال برقرار است.\n"
        f"mode=server generation={generation} rank={rank}\n"
        f"id={selected.get('id')}\n"
        f"remote={selected.get('host')}:{selected.get('port')}\n"
        f"public_port={public_port}\n"
        f"ip={result.get('public_ip')}",
    )


def blocked_ipinfo_body(body):
    text = (body or "").strip()
    if not text:
        return 0, ""

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for key in ("status", "statusCode", "code", "errorCode"):
                if key in parsed:
                    try:
                        code = int(parsed[key])
                    except Exception:
                        continue
                    if code in BLOCK_HTTP_STATUSES or code >= 400:
                        return code, f"body error code {code}"
            message = " ".join(str(parsed.get(k) or "") for k in ("error", "message", "msg", "reason"))
            lowered_msg = message.lower()
            if any(token in lowered_msg for token in ("forbidden", "permission", "access denied", "blocked", "deny")):
                return 403, message[:160] or "body forbidden"
    except Exception:
        pass

    lowered = re.sub(r"\s+", " ", text.lower())
    if (
        "403 forbidden" in lowered
        or "error: forbidden" in lowered
        or "forbidden" in lowered
        or "does not have permission" in lowered
        or "access denied" in lowered
        or "permission denied" in lowered
        or "request blocked" in lowered
    ):
        return 403, "body forbidden/access denied"
    if re.search(r"\b(?:error|code|status|statuscode)[\"':= ]+\s*(?:400|401|403|407|429|451)\b", lowered):
        match = re.search(r"\b(400|401|403|407|429|451)\b", lowered)
        code = int(match.group(1)) if match else 403
        return code, f"body error code {code}"
    return 0, ""


def curl_status_ip(port, socks_host="127.0.0.1", urls=None):
    """Check public IP through SOCKS and preserve HTTP status.

    Returns a dict with:
      ok=True when a 2xx response contains a valid IP
      forbidden=True when any probe returns HTTP/body blocked status
      ip/status/url/error for diagnostics
    """
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        return {"ok": False, "forbidden": False, "ip": None, "status": 0, "url": "", "error": "curl not found"}
    errors = []
    for url in urls or AUTO_IPINFO_URLS:
        args = [
            curl,
            "-sS",
            "--connect-timeout",
            "5",
            "--max-time",
            "12",
            "--socks5-hostname",
            f"{socks_host}:{port}",
            "-w",
            "\n__HTTP_STATUS__:%{http_code}",
        ]
        if url.startswith("https://"):
            args.append("--insecure")
        args.append(url)
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=18)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue
        raw = p.stdout or ""
        match = re.search(r"\n__HTTP_STATUS__:(\d{3})\s*$", raw)
        status = int(match.group(1)) if match else 0
        body = raw[: match.start()].strip() if match else raw.strip()
        ip = normalize_ip_response(body)
        body_status, body_block_reason = blocked_ipinfo_body(body)
        if status in BLOCK_HTTP_STATUSES or body_status:
            return {
                "ok": False,
                "forbidden": True,
                "ip": ip,
                "status": body_status or status,
                "url": url,
                "error": body_block_reason or f"HTTP {status}",
            }
        if 200 <= status < 300 and ip:
            return {
                "ok": True,
                "forbidden": False,
                "ip": ip,
                "status": status,
                "url": url,
                "error": "",
            }
        if p.returncode != 0:
            errors.append(f"{url}: curl exit={p.returncode} stderr={p.stderr.strip()[:160]!r} status={status}")
        elif status:
            errors.append(f"{url}: status={status} invalid_ip={body[:120]!r}")
        else:
            errors.append(f"{url}: no http status body={body[:120]!r}")
        if socks_host in {"127.0.0.1", "localhost"} and not port_open(port):
            errors.append(f"{url}: local socks listener {socks_host}:{port} closed during auto check")
            break
    return {
        "ok": False,
        "forbidden": False,
        "ip": None,
        "status": 0,
        "url": "",
        "error": " | ".join(errors[-4:])[:1000],
    }


def probe_socks_path(port, socks_host, probes, max_failures, delay_ms, label):
    probes = max(1, int(probes))
    max_failures = max(0, int(max_failures))
    delay_s = max(0, int(delay_ms)) / 1000.0
    successes = []
    failures = []

    for index in range(probes):
        url = PROBE_URLS[index % len(PROBE_URLS)]
        out, err, checked_url = curl_single_ip(port, socks_host, url)
        if out:
            successes.append({"index": index + 1, "ip": out, "url": checked_url})
        else:
            failures.append({"index": index + 1, "url": checked_url, "error": err[:240]})
        if index + 1 < probes and delay_s:
            time.sleep(delay_s)

    ok = len(failures) <= max_failures
    ip = successes[-1]["ip"] if successes else None
    checked_url = successes[-1]["url"] if successes else ""
    if ok:
        print(
            f"{label}_PROBE_OK successes={len(successes)}/{probes} "
            f"failures={len(failures)} max_failures={max_failures} ip={ip}"
        )
    else:
        print(
            f"{label}_PROBE_FAIL successes={len(successes)}/{probes} "
            f"failures={len(failures)} max_failures={max_failures} "
            f"errors={json.dumps(failures[-3:], ensure_ascii=False)}"
        )
    return ok, ip, checked_url, successes, failures


def run_quiet(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=20)


class TcpForwarder:
    def __init__(
        self,
        listen_address,
        listen_port,
        target_host,
        target_port,
        max_clients=8,
        upstream_retries=8,
        stream_retries=2,
        initial_buffer_bytes=262144,
        relay_buffer_bytes=262144,
    ):
        self.listen_address = listen_address
        self.listen_port = int(listen_port)
        self.target_host = target_host
        self.target_port = int(target_port)
        self.max_clients = max(1, int(max_clients))
        self.upstream_retries = max(1, int(upstream_retries))
        self.stream_retries = max(0, int(stream_retries))
        self.initial_buffer_bytes = max(0, int(initial_buffer_bytes))
        self.relay_buffer_bytes = max(65536, int(relay_buffer_bytes))
        self.client_slots = threading.BoundedSemaphore(self.max_clients)
        self.activity_lock = threading.Lock()
        self.active_clients = 0
        self.last_activity = 0.0
        self.stop_event = threading.Event()
        self.server = None

    def _tune_socket(self, sock):
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass
        for option in (socket.SO_RCVBUF, socket.SO_SNDBUF):
            try:
                sock.setsockopt(socket.SOL_SOCKET, option, self.relay_buffer_bytes)
            except Exception:
                pass

    def start(self):
        last_error = None
        for _ in range(12):
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.listen_address, self.listen_port))
                server.listen(128)
                self.server = server
                break
            except OSError as exc:
                last_error = exc
                try:
                    server.close()
                except Exception:
                    pass
                time.sleep(0.25)
        else:
            raise RuntimeError(f"public relay bind failed on {self.listen_address}:{self.listen_port}: {last_error}")

        threading.Thread(target=self._accept_loop, name="public-socks-relay", daemon=True).start()
        return self

    def stop(self):
        self.stop_event.set()
        if self.server is not None:
            try:
                self.server.close()
            except Exception:
                pass

    def update_target(self, target_host, target_port):
        self.target_host = target_host
        self.target_port = int(target_port)

    def mark_activity(self, active_delta=0):
        with self.activity_lock:
            self.last_activity = time.time()
            if active_delta:
                self.active_clients = max(0, self.active_clients + active_delta)

    def recently_active(self, seconds):
        with self.activity_lock:
            return self.active_clients > 0 or (time.time() - self.last_activity) < max(0, seconds)

    def _accept_loop(self):
        while not self.stop_event.is_set():
            try:
                client, _addr = self.server.accept()
            except OSError:
                break
            self._tune_socket(client)
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _connect_upstream(self):
        last_error = None
        for _ in range(self.upstream_retries):
            if self.stop_event.is_set():
                break
            target_host = self.target_host
            target_port = self.target_port
            try:
                upstream = socket.create_connection((target_host, target_port), timeout=8)
                self._tune_socket(upstream)
                return upstream
            except OSError as exc:
                last_error = exc
                time.sleep(0.25)
        raise RuntimeError(f"upstream connect failed: {last_error}")

    def _recv_exact(self, sock, size):
        chunks = []
        remaining = int(size)
        while remaining > 0:
            data = sock.recv(remaining)
            if not data:
                raise RuntimeError("unexpected eof")
            chunks.append(data)
            remaining -= len(data)
        return b"".join(chunks)

    def _read_socks_request_from_client(self, client):
        client.settimeout(8)
        head = self._recv_exact(client, 2)
        if head[0] != 5:
            raise RuntimeError("only SOCKS5 is supported")
        methods = self._recv_exact(client, head[1])
        if b"\x00" not in methods:
            client.sendall(b"\x05\xff")
            raise RuntimeError("SOCKS5 no-auth method is required")
        client.sendall(b"\x05\x00")

        req_head = self._recv_exact(client, 4)
        if req_head[0] != 5 or req_head[1] != 1:
            try:
                client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            except Exception:
                pass
            raise RuntimeError("only SOCKS5 CONNECT is supported")

        atyp = req_head[3]
        if atyp == 1:
            addr = self._recv_exact(client, 4)
            addr_part = addr
        elif atyp == 3:
            length = self._recv_exact(client, 1)
            addr = self._recv_exact(client, length[0])
            addr_part = length + addr
        elif atyp == 4:
            addr = self._recv_exact(client, 16)
            addr_part = addr
        else:
            try:
                client.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
            except Exception:
                pass
            raise RuntimeError("unsupported SOCKS5 address type")

        port = self._recv_exact(client, 2)
        client.settimeout(None)
        return req_head + addr_part + port

    def _read_socks_response_from_upstream(self, upstream):
        head = self._recv_exact(upstream, 4)
        atyp = head[3]
        if atyp == 1:
            addr_part = self._recv_exact(upstream, 4)
        elif atyp == 3:
            length = self._recv_exact(upstream, 1)
            addr_part = length + self._recv_exact(upstream, length[0])
        elif atyp == 4:
            addr_part = self._recv_exact(upstream, 16)
        else:
            raise RuntimeError("invalid upstream SOCKS5 address type")
        port = self._recv_exact(upstream, 2)
        return head + addr_part + port

    def _connect_native_socks(self, request_bytes):
        last_error = None
        for _ in range(self.upstream_retries):
            upstream = None
            try:
                upstream = self._connect_upstream()
                upstream.settimeout(20)
                upstream.sendall(b"\x05\x01\x00")
                method = self._recv_exact(upstream, 2)
                if method != b"\x05\x00":
                    raise RuntimeError(f"native SOCKS auth rejected: {method.hex()}")
                upstream.sendall(request_bytes)
                response = self._read_socks_response_from_upstream(upstream)
                if len(response) < 2 or response[1] != 0:
                    raise RuntimeError(f"native SOCKS connect failed: {response.hex()}")
                upstream.settimeout(None)
                return upstream, response
            except Exception as exc:
                last_error = exc
                if upstream is not None:
                    try:
                        upstream.close()
                    except Exception:
                        pass
                time.sleep(0.25)
        raise RuntimeError(f"native SOCKS connect failed after retries: {last_error}")

    def _reconnect_and_replay(self, request_bytes, replay_buffer, attempt):
        upstream, _response = self._connect_native_socks(request_bytes)
        if replay_buffer:
            upstream.sendall(bytes(replay_buffer))
        print(f"PUBLIC_REPLAY_RETRY attempt={attempt} bytes={len(replay_buffer)}")
        return upstream

    def _handle_client(self, client):
        upstream = None
        acquired = False
        try:
            request_bytes = self._read_socks_request_from_client(client)

            acquired = self.client_slots.acquire(timeout=5)
            if not acquired:
                try:
                    client.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
                except Exception:
                    pass
                return
            self.mark_activity(active_delta=1)
            try:
                upstream, response = self._connect_native_socks(request_bytes)
            except Exception:
                try:
                    client.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
                except Exception:
                    pass
                return
            client.sendall(response)

            upstream_app_seen = False
            replay_buffer = bytearray()
            replay_attempts = 0
            sockets = [client, upstream]
            while not self.stop_event.is_set():
                readable, _, exceptional = select.select(sockets, [], sockets, 1.0)
                if exceptional:
                    break
                for src in readable:
                    data = src.recv(self.relay_buffer_bytes)
                    if not data:
                        if (
                            src is upstream
                            and not upstream_app_seen
                            and replay_buffer
                            and replay_attempts < self.stream_retries
                        ):
                            replay_attempts += 1
                            try:
                                upstream.close()
                            except Exception:
                                pass
                            upstream = self._reconnect_and_replay(request_bytes, replay_buffer, replay_attempts)
                            sockets = [client, upstream]
                            continue
                        return
                    self.mark_activity()
                    if src is client:
                        if not upstream_app_seen and len(replay_buffer) < self.initial_buffer_bytes:
                            available = self.initial_buffer_bytes - len(replay_buffer)
                            replay_buffer.extend(data[:available])
                        try:
                            upstream.sendall(data)
                        except OSError:
                            if (
                                not upstream_app_seen
                                and replay_buffer
                                and replay_attempts < self.stream_retries
                            ):
                                replay_attempts += 1
                                try:
                                    upstream.close()
                                except Exception:
                                    pass
                                upstream = self._reconnect_and_replay(request_bytes, replay_buffer, replay_attempts)
                                sockets = [client, upstream]
                                continue
                            return
                    else:
                        upstream_app_seen = True
                        if replay_buffer:
                            replay_buffer.clear()
                        client.sendall(data)
        except Exception:
            pass
        finally:
            for s in (client, upstream):
                if s is not None:
                    try:
                        s.close()
                    except Exception:
                        pass
            if acquired:
                try:
                    self.mark_activity(active_delta=-1)
                    self.client_slots.release()
                except ValueError:
                    pass


def expose_public_port(
    public_port,
    local_socks_port,
    listen_address,
    allow_from_ip,
    max_clients=8,
    upstream_retries=8,
    stream_retries=2,
    initial_buffer_bytes=262144,
    relay_buffer_bytes=262144,
):
    if os.name == "nt":
        # Clear stale netsh portproxy listeners from older runs. The current version
        # uses an in-process TCP relay, so the public port closes when this process exits.
        for address in {listen_address, "0.0.0.0"}:
            run_quiet([
                "netsh", "interface", "portproxy", "delete", "v4tov4",
                f"listenaddress={address}", f"listenport={int(public_port)}",
            ])

        if listen_address not in {"127.0.0.1", "localhost", "::1"}:
            rule_name = f"JumpJumpProxy-{int(public_port)}"
            ps = [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                (
                    f"Remove-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue; "
                    f"New-NetFirewallRule -DisplayName '{rule_name}' -Direction Inbound -Action Allow "
                    f"-Protocol TCP -LocalPort {int(public_port)}"
                    + (f" -RemoteAddress '{allow_from_ip}'" if allow_from_ip else "")
                    + " | Out-Null"
                ),
            ]
            fw = run_quiet(ps)
            if fw.returncode != 0:
                raise RuntimeError(fw.stderr.strip() or fw.stdout.strip() or "firewall rule failed")
    elif allow_from_ip:
        print(
            "PUBLIC_FIREWALL_WARNING=allow_from_ip_not_enforced_on_linux "
            "Use ufw/iptables/security-group to restrict the public port.",
            flush=True,
        )

    return TcpForwarder(
        listen_address,
        int(public_port),
        "127.0.0.1",
        int(local_socks_port),
        max_clients=max_clients,
        upstream_retries=upstream_retries,
        stream_retries=stream_retries,
        initial_buffer_bytes=initial_buffer_bytes,
        relay_buffer_bytes=relay_buffer_bytes,
    ).start()


def stop_connector(base, timeout=10):
    try:
        return post(base, "/api/proxy_connector_stop", {}, timeout=timeout)
    except Exception as exc:
        print(f"STOP_WARNING={exc}")
        return None


def fetch_candidate_list(args, generation):
    original = (
        refresh_profile_from_api(args.base, args.group_code, args.refresh_country, args.refresh_lang, args.ad_media_platform)
        if args.refresh else load_json(args.profile)
    )
    found = candidates(original, args.mode, args.ping_timeout)
    print(f"CANDIDATE_LIST generation={generation} count={len(found)} mode={args.mode}")
    for index, candidate in enumerate(found[:12], 1):
        extra = ""
        if candidate.get("purpose") == "adpair":
            extra = (
                f" ad_id={candidate.get('ad_id')} "
                f"ad_remote={candidate.get('ad_host')}:{candidate.get('ad_port')} "
                f"ad_latency={candidate.get('ad_latency_ms')}ms"
            )
        print(
            "CANDIDATE "
            f"rank={index} purpose={candidate['purpose']} id={candidate['id']} "
            f"remote={candidate['host']}:{candidate['port']} "
            f"real={candidate.get('real_ping_ms')}ms/{candidate.get('real_ping_source')} "
            f"tcp={candidate.get('latency_ms')}ms ping_ip={candidate.get('ping_ip') or candidate.get('ip')}"
            f"{extra}"
        )
    return original, found


def write_runtime_status(status, **values):
    state = {
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
    }
    state.update(values)
    save_json(RUNTIME / "active_state.json", state)


def try_start_candidate(args, original, selected, generation, rank):
    profile = prioritize(original, selected)
    save_json(RUNTIME / "native_selected_profile.json", profile)
    socks_port, payload = build_start_payload(profile, args.assets_dir, args.skip_measure, args.no_tun2socks)
    save_json(RUNTIME / "native_start_payload.json", payload)

    if selected["purpose"] == "adpair":
        label = "AD-PAIR"
    elif selected["purpose"] == "ad":
        label = "AD-CONFIG"
    else:
        label = "APP-CONFIG"
    extra = ""
    if selected.get("purpose") == "adpair":
        extra = (
            f" normal_id={selected.get('normal_id')} "
            f"ad_id={selected.get('ad_id')} "
            f"ad_remote={selected.get('ad_host')}:{selected.get('ad_port')} "
            f"ad_latency={selected.get('ad_latency_ms')}ms"
        )
    print(
        "TRY_CANDIDATE "
        f"generation={generation} rank={rank} {label} id={selected['id']} "
        f"remote={selected['host']}:{selected['port']} "
        f"real={selected.get('real_ping_ms')}ms/{selected.get('real_ping_source')} "
        f"tcp={selected.get('latency_ms')}ms ping_ip={selected.get('ping_ip') or selected.get('ip')}"
        f"{extra}"
    )

    stop_connector(args.base, timeout=8)
    try:
        started = post(args.base, "/api/proxy_connector_start", payload, timeout=50)
    except Exception as exc:
        if not sdk_stat_ok(args.base):
            write_runtime_status(
                "sdk_unavailable",
                generation=generation,
                rank=rank,
                mode=args.mode,
                selected={k: selected.get(k) for k in ("purpose", "id", "host", "port", "latency_ms")},
                error=f"SDK stopped responding during proxy_connector_start: {exc}",
            )
            raise RuntimeError(f"SDK stopped responding during proxy_connector_start: {exc}") from exc
        write_runtime_status(
            "candidate_start_http_failed",
            generation=generation,
            rank=rank,
            mode=args.mode,
            selected={k: selected.get(k) for k in ("purpose", "id", "host", "port", "latency_ms")},
            error=str(exc),
        )
        return None, f"{label} id={selected['id']} connector_start_http_error={exc}"
    if not started.get("success"):
        write_runtime_status(
            "candidate_start_failed",
            generation=generation,
            rank=rank,
            mode=args.mode,
            selected={k: selected.get(k) for k in ("purpose", "id", "host", "port", "latency_ms")},
            error=started.get("errorMessage") or started,
        )
        return None, f"{label} id={selected['id']} start_failed={started.get('errorMessage') or started}"
    print(f"CONNECTOR_START_OK {label} id={selected['id']} remote={selected['host']}:{selected['port']}")

    active_channel = channels(nodes(profile)[0])[0]
    try:
        set_active = post(args.base, "/api/proxy_service_set_active_proxy_node_channel", active_channel, timeout=12)
    except Exception as exc:
        if not sdk_stat_ok(args.base):
            write_runtime_status(
                "sdk_unavailable",
                generation=generation,
                rank=rank,
                mode=args.mode,
                selected={k: selected.get(k) for k in ("purpose", "id", "host", "port", "latency_ms")},
                error=f"SDK stopped responding during set_active_channel: {exc}",
            )
            raise RuntimeError(f"SDK stopped responding during set_active_channel: {exc}") from exc
        stop_connector(args.base, timeout=10)
        write_runtime_status(
            "candidate_set_active_http_failed",
            generation=generation,
            rank=rank,
            mode=args.mode,
            selected={k: selected.get(k) for k in ("purpose", "id", "host", "port", "latency_ms")},
            error=str(exc),
        )
        return None, f"{label} id={selected['id']} set_active_http_error={exc}"
    if not set_active.get("success"):
        stop_connector(args.base, timeout=10)
        write_runtime_status(
            "candidate_set_active_failed",
            generation=generation,
            rank=rank,
            mode=args.mode,
            selected={k: selected.get(k) for k in ("purpose", "id", "host", "port", "latency_ms")},
            error=set_active.get("errorMessage") or set_active,
        )
        return None, f"{label} id={selected['id']} set_active_failed={set_active.get('errorMessage') or set_active}"
    deadline = time.time() + args.start_wait
    while time.time() < deadline and not port_open(socks_port):
        time.sleep(0.2)

    ok, out, checked_url, successes, failures = probe_socks_path(
        socks_port,
        "127.0.0.1",
        args.stability_probes,
        args.stability_max_failures,
        args.stability_delay_ms,
        "STARTUP",
    )
    if not ok:
        stop_connector(args.base, timeout=10)
        err = " | ".join(f"{f['url']}: {f['error']}" for f in failures[-5:]) or "startup probe failed"
        write_runtime_status(
            "candidate_health_failed",
            generation=generation,
            rank=rank,
            mode=args.mode,
            selected={k: selected.get(k) for k in ("purpose", "id", "host", "port", "latency_ms")},
            socks=f"127.0.0.1:{socks_port}",
            portOpen=port_open(socks_port),
            probeSuccesses=successes,
            probeFailures=failures,
            error=err[:1000],
        )
        return None, (
            f"{label} id={selected['id']} remote={selected['host']}:{selected['port']} "
            f"socks=127.0.0.1:{socks_port} port_open={port_open(socks_port)} startup_probe_error={err[:240]}"
        )

    state = {
        "status": "active",
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "configSource": "live_api" if args.refresh else "profile_file",
        "generation": generation,
        "rank": rank,
        "mode": args.mode,
        "selected": selected,
        "socks": f"127.0.0.1:{socks_port}",
        "publicIp": out,
        "publicIpCheckUrl": checked_url,
        "startupProbeSuccesses": successes,
        "startupProbeFailures": failures,
    }
    save_json(RUNTIME / "active_state.json", state)
    print("STARTED_NATIVE")
    print(f"selected={label} id={selected['id']} remote={selected['host']}:{selected['port']} latency={selected['latency_ms']}ms")
    print(f"SOCKS5=127.0.0.1:{socks_port}")
    print(f"SET_ACTIVE={json.dumps(set_active, ensure_ascii=False)}")
    print(f"PORT_OPEN={port_open(socks_port)}")
    print(f"PUBLIC_IP_CHECK_URL={checked_url}")
    print(f"PUBLIC_IP={out}")
    return {
        "profile": profile,
        "selected": selected,
        "label": label,
        "socks_port": socks_port,
        "public_ip": out,
        "checked_url": checked_url,
        "generation": generation,
        "rank": rank,
    }, ""


def main():
    ap = argparse.ArgumentParser(description="Start JumpJump native Windows SDK with app-like AD-pair or app channels.")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE))
    ap.add_argument("--refresh", action="store_true", help="fetch a fresh profile from JumpJump APIs before selecting nodes")
    ap.add_argument("--group-code", default="autonewir", help="group code used with --refresh; default: autonewir")
    ap.add_argument("--refresh-country", default="IR", help="countryCode used in fresh API fingerprint; default: IR")
    ap.add_argument("--refresh-lang", default="fa", help="lang/languageCode used in fresh API fingerprint; default: fa")
    ap.add_argument("--ad-media-platform", default="admob", help="adMediaPlatform used in fresh guest login; default: admob")
    ap.add_argument("--assets-dir", default=str(DEFAULT_ASSETS))
    ap.add_argument(
        "--mode",
        choices=("ad", "ads", "adonly", "app", "normal", "smart", "all"),
        default="ad",
        help=(
            "ad/ads = app-like normal+AD pairs first, then raw AD fallback; "
            "app/normal/smart = normal app channels; adonly = old raw AD-channel-as-default test"
        ),
    )
    ap.add_argument("--ping-timeout", type=float, default=1.8)
    ap.add_argument("--skip-measure", action="store_true")
    ap.add_argument("--no-tun2socks", action="store_true", help="do not send tun2SocksStartOptions; useful for Linux/Wine where Windows TUN APIs are unavailable")
    ap.add_argument("--public-port", type=int, default=0, help="optional public TCP port to forward to the selected local SOCKS5 port")
    ap.add_argument("--public-listen", default="0.0.0.0", help="listen address for --public-port; default: 0.0.0.0")
    ap.add_argument("--allow-from-ip", default="", help="optional firewall RemoteAddress for --public-port, e.g. your client IP")
    ap.add_argument("--public-max-connections", type=int, default=8, help="max concurrent public relay connections; default 8 keeps browsers/apps from stalling on one SOCKS port")
    ap.add_argument("--public-upstream-retries", type=int, default=8, help="retries from public relay to local native SOCKS before closing a client")
    ap.add_argument("--public-stream-retries", type=int, default=2, help="replay initial client payload if native SOCKS closes before first upstream payload")
    ap.add_argument("--public-initial-buffer-bytes", type=int, default=262144, help="max initial client payload bytes buffered for replay")
    ap.add_argument("--public-relay-buffer-bytes", type=int, default=262144, help="TCP relay read/write buffer size")
    ap.add_argument("--public-health-url", default="http://ifconfig.me/ip", help="strict URL used to validate --public-port before accepting a config")
    ap.add_argument("--health-interval", type=int, default=30, help="seconds between SOCKS health checks in long-running mode")
    ap.add_argument("--health-failures", type=int, default=2, help="consecutive failed health checks before rotating config")
    ap.add_argument("--health-probes", type=int, default=1, help="number of real SOCKS requests per health interval")
    ap.add_argument("--health-probe-max-failures", type=int, default=0, help="allowed failed requests inside one health interval")
    ap.add_argument("--health-probe-delay-ms", type=int, default=600, help="delay between health probe requests")
    ap.add_argument("--health-via-public", action="store_true", help="run watchdog through public relay; default uses native SOCKS to avoid competing with external clients")
    ap.add_argument("--skip-health-when-public-active-seconds", type=int, default=30, help="skip internal watchdog checks after public client activity to avoid competing with real traffic")
    ap.add_argument("--reconnect-delay", type=int, default=0, help="seconds to wait before trying the next candidate or refreshing after a failure")
    ap.add_argument("--max-reconnects", type=int, default=0, help="0 means reconnect forever")
    ap.add_argument("--start-wait", type=int, default=15, help="seconds to wait for the local SOCKS listener after native start")
    ap.add_argument("--stability-probes", type=int, default=3, help="real SOCKS requests required before accepting a candidate")
    ap.add_argument("--stability-max-failures", type=int, default=0, help="allowed failed startup probes before rejecting a candidate")
    ap.add_argument("--stability-delay-ms", type=int, default=700, help="delay between startup stability probes")
    ap.add_argument("--once", action="store_true", help="start, print/test, then stop")
    ap.add_argument("--hold", type=int, default=0, help="seconds to keep running with --once")
    args = ap.parse_args()
    args.requested_mode = args.mode
    args.mode = normalize_mode(args.mode)

    telegram_config = load_telegram_config()
    no_proxy_notified = False
    last_found_key = ""
    public_forwarder = None
    reconnects = 0
    generation = 0
    original = None
    found = []
    candidate_index = 0
    generation_failures = []

    try:
        while True:
            if original is None or candidate_index >= len(found):
                if found:
                    print(
                        "CANDIDATE_LIST_EXHAUSTED "
                        f"generation={generation} tried={len(found)} failures={len(generation_failures)} "
                        "action=fetch_new_live_api"
                    )
                    write_runtime_status(
                        "candidate_list_exhausted",
                        generation=generation,
                        mode=args.mode,
                        tried=len(found),
                        failures=generation_failures[-50:],
                        action="fetch_new_live_api",
                    )
                    for failure in generation_failures[-12:]:
                        print(f"GENERATION_FAILURE generation={generation} {failure}")
                    if not no_proxy_notified:
                        notify_no_proxy(
                            telegram_config,
                            "candidate list exhausted: " + " | ".join(generation_failures[-5:]),
                            generation,
                            args.mode,
                            reconnects,
                        )
                        no_proxy_notified = True

                generation += 1
                original = None
                found = []
                candidate_index = 0
                generation_failures = []

                try:
                    original, found = fetch_candidate_list(args, generation)
                    write_runtime_status(
                        "searching",
                        generation=generation,
                        mode=args.mode,
                        candidates=len(found),
                        action="try_candidates",
                    )
                except Exception as exc:
                    reconnects += 1
                    print(f"FETCH_LIST_FAIL generation={generation} reconnect={reconnects} error={exc}")
                    write_runtime_status(
                        "fetch_list_failed",
                        generation=generation,
                        mode=args.mode,
                        reconnect=reconnects,
                        error=str(exc),
                    )
                    if not no_proxy_notified:
                        notify_no_proxy(telegram_config, f"fetch live API list failed: {exc}", generation, args.mode, reconnects)
                        no_proxy_notified = True
                    if args.once:
                        raise
                    if args.max_reconnects and reconnects > args.max_reconnects:
                        raise RuntimeError(f"max reconnects exceeded: {args.max_reconnects}") from exc
                    time.sleep(max(0, args.reconnect_delay))
                    continue
                if not found:
                    reconnects += 1
                    print(f"CANDIDATE_LIST_EMPTY generation={generation} reconnect={reconnects} action=fetch_new_live_api")
                    write_runtime_status(
                        "candidate_list_empty",
                        generation=generation,
                        mode=args.mode,
                        reconnect=reconnects,
                        action="fetch_new_live_api",
                    )
                    if not no_proxy_notified:
                        notify_no_proxy(telegram_config, "fresh API returned zero candidates", generation, args.mode, reconnects)
                        no_proxy_notified = True
                    if args.once:
                        raise RuntimeError("fresh API returned zero candidates")
                    time.sleep(max(0, args.reconnect_delay))
                    continue

            selected = found[candidate_index]
            rank = candidate_index + 1
            candidate_index += 1

            result, failure = try_start_candidate(args, original, selected, generation, rank)
            if result is None:
                print(f"ATTEMPT_FAILED generation={generation} rank={rank} {failure}")
                generation_failures.append(f"rank={rank} {failure}")
                if args.once and candidate_index >= len(found):
                    raise RuntimeError("no working proxy after trying candidates")
                continue

            socks_port = result["socks_port"]

            if args.public_port:
                if public_forwarder is None:
                    public_forwarder = expose_public_port(
                        args.public_port,
                        socks_port,
                        args.public_listen,
                        args.allow_from_ip,
                        args.public_max_connections,
                        args.public_upstream_retries,
                        args.public_stream_retries,
                        args.public_initial_buffer_bytes,
                        args.public_relay_buffer_bytes,
                    )
                    print(f"PUBLIC_SOCKS5={args.public_listen}:{args.public_port}")
                    print("PUBLIC_FORWARDER=python-relay")
                    print(f"PUBLIC_FORWARDER_MAX_CONNECTIONS={args.public_max_connections}")
                    print(f"PUBLIC_FORWARDER_UPSTREAM_RETRIES={args.public_upstream_retries}")
                    print(f"PUBLIC_FORWARDER_STREAM_RETRIES={args.public_stream_retries}")
                    print(f"PUBLIC_FORWARDER_RELAY_BUFFER_BYTES={args.public_relay_buffer_bytes}")
                    if args.allow_from_ip:
                        print(f"PUBLIC_FIREWALL_ALLOW_FROM={args.allow_from_ip}")
                else:
                    public_forwarder.update_target("127.0.0.1", socks_port)
                    print(f"PUBLIC_FORWARDER_TARGET=127.0.0.1:{socks_port}")

                if args.public_health_url:
                    selected_desc = (
                        f"purpose={selected.get('purpose')} id={selected.get('id')} "
                        f"remote={selected.get('host')}:{selected.get('port')}"
                    )
                    public_check = curl_status_ip(
                        args.public_port,
                        "127.0.0.1",
                        urls=[args.public_health_url],
                    )
                    if not public_check.get("ok"):
                        public_error = (
                            f"url={public_check.get('url') or args.public_health_url} "
                            f"status={public_check.get('status')} error={public_check.get('error')}"
                        )
                        print(
                            "PUBLIC_HEALTH_FAIL "
                            f"generation={generation} rank={rank} {selected_desc} {public_error[:240]}"
                        )
                        generation_failures.append(
                            f"rank={rank} {selected_desc} public_health_failed {public_error}"
                        )
                        stop_connector(args.base, timeout=10)
                        if args.once and candidate_index >= len(found):
                            raise RuntimeError("no working public proxy after trying candidates")
                        continue
                    print(
                        "PUBLIC_HEALTH_OK "
                        f"ip={public_check.get('ip')} status={public_check.get('status')} "
                        f"url={public_check.get('url')}"
                    )

            selected_key = candidate_key(selected)
            if selected_key != last_found_key or no_proxy_notified:
                notify_proxy_found(telegram_config, selected, result, generation, rank, args.public_port)
                last_found_key = selected_key
                no_proxy_notified = False

            health_host = "127.0.0.1"
            health_port = args.public_port if args.public_port and args.health_via_public else socks_port
            health_path = "public_relay" if args.public_port and args.health_via_public else "native_socks"

            if args.once:
                if args.hold > 0:
                    time.sleep(args.hold)
                if public_forwarder is not None:
                    public_forwarder.stop()
                stop_connector(args.base, timeout=10)
                return

            print(
                "WATCHDOG=enabled "
                f"interval={args.health_interval}s failures={args.health_failures} reconnect_delay={args.reconnect_delay}s "
                f"target={health_path}:{health_host}:{health_port}"
            )
            print("Running. Watchdog will refresh/rotate automatically. Press Ctrl+C to stop.")

            fail_count = 0
            last_ip = result["public_ip"]
            while True:
                time.sleep(max(1, args.health_interval))
                if (
                    public_forwarder is not None
                    and not args.health_via_public
                    and args.skip_health_when_public_active_seconds > 0
                    and public_forwarder.recently_active(args.skip_health_when_public_active_seconds)
                ):
                    print(
                        "HEALTH_SKIPPED "
                        f"reason=recent_public_activity seconds={args.skip_health_when_public_active_seconds}"
                    )
                    fail_count = 0
                    continue
                ok, out, checked_url, successes, failures = probe_socks_path(
                    health_port,
                    health_host,
                    args.health_probes,
                    args.health_probe_max_failures,
                    args.health_probe_delay_ms,
                    "HEALTH",
                )
                if ok and out:
                    if out != last_ip:
                        print(f"HEALTH_OK_IP_CHANGED old={last_ip} new={out} url={checked_url}")
                        last_ip = out
                    else:
                        print(f"HEALTH_OK ip={out} url={checked_url}")
                    fail_count = 0
                    continue

                fail_count += 1
                err = " | ".join(f"{f['url']}: {f['error']}" for f in failures[-5:]) or "health probe failed"
                print(f"HEALTH_FAIL count={fail_count}/{args.health_failures} error={err[:240]}")
                if fail_count >= max(1, args.health_failures):
                    reconnects += 1
                    print(
                        "ROTATE_CONFIG "
                        f"reason=health_failed reconnect={reconnects} generation={generation} "
                        f"failed_rank={result['rank']} next_rank={candidate_index + 1 if candidate_index < len(found) else 'fetch_new_list'}"
                    )
                    stop_connector(args.base, timeout=10)
                    if args.max_reconnects and reconnects > args.max_reconnects:
                        raise RuntimeError(f"max reconnects exceeded: {args.max_reconnects}")
                    if candidate_index >= len(found):
                        print(f"ROTATE_QUEUE_EXHAUSTED generation={generation} action=fetch_new_live_api")
                    time.sleep(max(0, args.reconnect_delay))
                    break
    except KeyboardInterrupt:
        print("STOP_REQUESTED=keyboard")
        if public_forwarder is not None:
            public_forwarder.stop()
        stop_connector(args.base, timeout=10)


if __name__ == "__main__":
    main()
