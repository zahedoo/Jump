#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from jumpjump_native_proxy import (
    DEFAULT_ASSETS,
    DEFAULT_BASE,
    DEFAULT_PROFILE,
    RUNTIME,
    candidates,
    channels,
    expose_public_port,
    load_json,
    normalize_mode,
    nodes,
    probe_socks_path,
    refresh_profile_from_api,
    stop_connector,
    try_start_candidate,
)


def candidate_kind(candidate):
    purpose = candidate.get("purpose")
    if purpose == "adpair":
        return "ADS-PAIR"
    if purpose == "ad":
        return "ADS-RAW"
    if purpose in ("app", "normal"):
        if candidate.get("ad_id"):
            return "NORMAL+AD"
        return "NORMAL"
    return str(purpose or "UNKNOWN").upper()


def channel_line(candidate, key="channel"):
    channel = candidate.get(key) or {}
    attrs = channel.get("nodeAttrs") or {}
    linkline = channel.get("linkline") or attrs.get("linkline") or {}
    country = linkline.get("country") or ""
    region = linkline.get("region") or ""
    line_type = linkline.get("type") or ""
    group = attrs.get("groupCode") or ""
    return {
        "country": country,
        "region": region,
        "type": line_type,
        "group": group,
    }


def format_ms(value, none_label="NO-PING"):
    if value is None:
        return none_label
    return f"{value}ms"


def format_real(candidate, prefix=""):
    value = candidate.get(prefix + "real_ping_ms")
    if value is None:
        return "NO-REAL"
    source = candidate.get(prefix + "real_ping_source") or "REAL"
    return f"{value}ms/{source}"


def compact_row(index, candidate):
    main = channel_line(candidate, "channel")
    kind = candidate_kind(candidate)
    ping = candidate.get("latency_ms")
    real = candidate.get("real_ping_ms")
    status = "[OK]" if real is not None else ("[TCP]" if ping is not None else "[NO]")
    remote = f"{candidate.get('host')}:{candidate.get('port')}"
    cid = candidate.get("id") or ""

    if candidate.get("purpose") == "adpair":
        ad_remote = f"{candidate.get('ad_host')}:{candidate.get('ad_port')}"
        return (
            f"{index:>2}) {status} {kind:<8} "
            f"normal={candidate.get('normal_id')} {remote:<22} ip={candidate.get('ip') or '-':<15} "
            f"ping_ip={candidate.get('ping_ip') or '-':<15} real={format_real(candidate):<11} tcp={format_ms(ping):<8} "
            f"ad={candidate.get('ad_id')} {ad_remote:<22} ad_ip={candidate.get('ad_ip') or '-':<15} "
            f"ad_ping_ip={candidate.get('ad_ping_ip') or '-':<15} ad_real={format_real(candidate, 'ad_'):<11} "
            f"ad_tcp={format_ms(candidate.get('ad_latency_ms')):<8} "
            f"{main.get('country') or '-'} {main.get('region') or ''}"
        )

    if candidate.get("ad_id"):
        ad_remote = f"{candidate.get('ad_host')}:{candidate.get('ad_port')}"
        return (
            f"{index:>2}) {status} {kind:<8} "
            f"normal={cid:<18} {remote:<22} ip={candidate.get('ip') or '-':<15} "
            f"ping_ip={candidate.get('ping_ip') or '-':<15} real={format_real(candidate):<11} tcp={format_ms(ping):<8} "
            f"ad={candidate.get('ad_id')} {ad_remote:<22} ad_ip={candidate.get('ad_ip') or '-':<15} "
            f"ad_ping_ip={candidate.get('ad_ping_ip') or '-':<15} ad_real={format_real(candidate, 'ad_'):<11} "
            f"ad_tcp={format_ms(candidate.get('ad_latency_ms')):<8} "
            f"{main.get('country') or '-'} {main.get('region') or ''}"
        )

    return (
        f"{index:>2}) {status} {kind:<8} "
        f"id={cid:<18} {remote:<22} ip={candidate.get('ip') or '-':<15} "
        f"ping_ip={candidate.get('ping_ip') or '-':<15} real={format_real(candidate):<11} tcp={format_ms(ping):<8} "
        f"{main.get('country') or '-'} {main.get('region') or ''}"
    )


def write_selection_list(path, mode, found):
    rows = []
    for index, candidate in enumerate(found, 1):
        rows.append(
            {
                "rank": index,
                "kind": candidate_kind(candidate),
                "purpose": candidate.get("purpose"),
                "id": candidate.get("id"),
                "normalId": candidate.get("normal_id"),
                "adId": candidate.get("ad_id"),
                "remote": f"{candidate.get('host')}:{candidate.get('port')}",
                "remoteIp": candidate.get("ip"),
                "pingIp": candidate.get("ping_ip"),
                "realPingMs": candidate.get("real_ping_ms"),
                "realPingSource": candidate.get("real_ping_source"),
                "tcpPingMs": candidate.get("latency_ms"),
                "pingMs": candidate.get("real_ping_ms"),
                "adRemote": (
                    f"{candidate.get('ad_host')}:{candidate.get('ad_port')}"
                    if candidate.get("ad_host")
                    else None
                ),
                "adRemoteIp": candidate.get("ad_ip"),
                "adPingIp": candidate.get("ad_ping_ip"),
                "adRealPingMs": candidate.get("ad_real_ping_ms"),
                "adRealPingSource": candidate.get("ad_real_ping_source"),
                "adTcpPingMs": candidate.get("ad_latency_ms"),
                "adPingMs": candidate.get("ad_real_ping_ms"),
                "line": channel_line(candidate, "channel"),
                "adLine": channel_line(candidate, "ad_channel") if candidate.get("ad_channel") else None,
            }
        )
    data = {
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": mode,
        "count": len(rows),
        "items": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_list(args, generation):
    mode = normalize_mode(args.mode)
    print(f"[WAIT] Fetching fresh API data ... generation={generation} mode={args.mode} normalized={mode}", flush=True)
    if args.refresh:
        profile = refresh_profile_from_api(
            args.base,
            args.group_code,
            args.refresh_country,
            args.refresh_lang,
            args.ad_media_platform,
        )
    else:
        profile = load_json(args.profile)

    print("[WAIT] Measuring Real/ICMP/HTTP ping and TCP reachability for configs ...", flush=True)
    found = candidates(profile, mode, args.ping_timeout)
    write_selection_list(RUNTIME / "manual_selection_last.json", mode, found)
    return profile, found


def candidate_block_reason(candidate, allow_unpinged=False, allow_raw_ad=False):
    if candidate.get("purpose") == "ad" and not allow_raw_ad:
        return "ADS-RAW is an advertising bridge channel, not a full connector route; use --allow-raw-ad to force it"
    if candidate.get("latency_ms") is None and not allow_unpinged:
        return "VPN TCP endpoint is not reachable; real ping alone is not enough to start the tunnel; use --allow-unpinged to force it"
    return ""


def print_menu(mode, found):
    print("")
    print(f"===== CONFIG LIST mode={mode} count={len(found)} =====")
    if not found:
        print("No configs found.")
        return
    for index, candidate in enumerate(found, 1):
        suffix = ""
        reason = candidate_block_reason(candidate)
        if reason:
            suffix = "  [SKIP: " + reason.split(";")[0] + "]"
        print(compact_row(index, candidate) + suffix)
    print("")
    print("Select: number = connect | r = refresh list | q = quit")


def read_choice(found, preselected):
    if preselected:
        return str(preselected).strip()
    while True:
        try:
            value = input("config> ").strip()
        except EOFError:
            return "q"
        if value:
            return value


def build_start_args(args, mode):
    return SimpleNamespace(
        base=args.base,
        assets_dir=args.assets_dir,
        skip_measure=args.skip_measure,
        start_wait=args.start_wait,
        stability_probes=args.stability_probes,
        stability_max_failures=args.stability_max_failures,
        stability_delay_ms=args.stability_delay_ms,
        mode=mode,
        refresh=bool(args.refresh),
    )


def connect_selected(args, profile, found, selected_index, generation):
    if selected_index < 1 or selected_index > len(found):
        print(f"[ERR] invalid selection: {selected_index}")
        return None, None

    selected = found[selected_index - 1]
    reason = candidate_block_reason(
        selected,
        allow_unpinged=args.allow_unpinged,
        allow_raw_ad=args.allow_raw_ad,
    )
    if reason:
        print(f"[ERR] selected config is not connectable: {reason}")
        return None, None

    print("")
    print(f"[TRY] Connecting selection #{selected_index}: {compact_row(selected_index, selected)}", flush=True)
    result, failure = try_start_candidate(
        build_start_args(args, normalize_mode(args.mode)),
        profile,
        selected,
        generation=generation,
        rank=selected_index,
    )
    if result is None:
        print(f"[FAIL] start failed: {failure}")
        return None, None

    forwarder = None
    if args.public_port:
        forwarder = expose_public_port(
            args.public_port,
            result["socks_port"],
            args.public_listen,
            args.allow_from_ip,
            args.public_max_connections,
            args.public_upstream_retries,
            args.public_stream_retries,
            args.public_initial_buffer_bytes,
        )
        print(f"[OK] PUBLIC_SOCKS5={args.public_listen}:{args.public_port}")
        print("[OK] PUBLIC_FORWARDER=python-relay")
    print(f"[OK] SELECTED={candidate_kind(selected)} id={selected.get('id')}")
    print(f"[OK] LOCAL_SOCKS5=127.0.0.1:{result['socks_port']}")
    print(f"[OK] PUBLIC_IP={result['public_ip']} via {result['checked_url']}")
    return result, forwarder


def health_loop(args, result, forwarder):
    if args.once:
        if args.hold > 0:
            time.sleep(args.hold)
        return "quit"

    print("")
    print(
        f"[RUN] Active on public port {args.public_port}. "
        "Ctrl+C = stop. If health fails, the menu will return."
    )
    fail_count = 0
    last_ip = result.get("public_ip")
    health_port = args.public_port if args.health_via_public and args.public_port else result["socks_port"]
    health_host = "127.0.0.1"

    while True:
        time.sleep(max(1, args.health_interval))
        if (
            forwarder is not None
            and not args.health_via_public
            and args.skip_health_when_public_active_seconds > 0
            and forwarder.recently_active(args.skip_health_when_public_active_seconds)
        ):
            print(f"[HEALTH] skipped: recent public activity")
            fail_count = 0
            continue

        ok, out, checked_url, successes, failures = probe_socks_path(
            health_port,
            health_host,
            args.health_probes,
            args.health_probe_max_failures,
            args.health_probe_delay_ms,
            "MANUAL_HEALTH",
        )
        if ok and out:
            if out != last_ip:
                print(f"[HEALTH] OK ip changed {last_ip} -> {out} url={checked_url}")
                last_ip = out
            else:
                print(f"[HEALTH] OK ip={out} url={checked_url}")
            fail_count = 0
            continue

        fail_count += 1
        err = " | ".join(f"{f['url']}: {f['error']}" for f in failures[-3:]) or "health failed"
        print(f"[HEALTH] FAIL {fail_count}/{args.health_failures}: {err[:240]}")
        if fail_count >= max(1, args.health_failures):
            print("[ROTATE] selected config became unhealthy; returning to menu.")
            return "menu"


def main():
    ap = argparse.ArgumentParser(description="Interactive JumpJump config selector.")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE))
    ap.add_argument("--refresh", action="store_true", help="fetch fresh live API data before listing")
    ap.add_argument("--mode", choices=("ad", "ads", "adonly", "app", "normal", "smart", "all"), default="all")
    ap.add_argument("--group-code", default="autonewir")
    ap.add_argument("--refresh-country", default="IR")
    ap.add_argument("--refresh-lang", default="fa")
    ap.add_argument("--ad-media-platform", default="admob")
    ap.add_argument("--assets-dir", default=str(DEFAULT_ASSETS))
    ap.add_argument("--ping-timeout", type=float, default=1.8)
    ap.add_argument("--start-wait", type=int, default=15)
    ap.add_argument("--stability-probes", type=int, default=2)
    ap.add_argument("--stability-max-failures", type=int, default=1)
    ap.add_argument("--stability-delay-ms", type=int, default=700)
    ap.add_argument("--skip-measure", action="store_true")
    ap.add_argument("--allow-unpinged", action="store_true")
    ap.add_argument("--allow-raw-ad", action="store_true")

    ap.add_argument("--public-port", type=int, default=10880)
    ap.add_argument("--public-listen", default="0.0.0.0")
    ap.add_argument("--allow-from-ip", default="")
    ap.add_argument("--public-max-connections", type=int, default=1)
    ap.add_argument("--public-upstream-retries", type=int, default=8)
    ap.add_argument("--public-stream-retries", type=int, default=2)
    ap.add_argument("--public-initial-buffer-bytes", type=int, default=262144)

    ap.add_argument("--health-interval", type=int, default=30)
    ap.add_argument("--health-failures", type=int, default=2)
    ap.add_argument("--health-probes", type=int, default=1)
    ap.add_argument("--health-probe-max-failures", type=int, default=0)
    ap.add_argument("--health-probe-delay-ms", type=int, default=600)
    ap.add_argument("--health-via-public", action="store_true")
    ap.add_argument("--skip-health-when-public-active-seconds", type=int, default=30)

    ap.add_argument("--select", type=int, default=0, help="non-interactive: select this row number")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--hold", type=int, default=0)
    args = ap.parse_args()

    args.mode = normalize_mode(args.mode)
    generation = 0
    preselected = args.select

    try:
        while True:
            generation += 1
            profile, found = fetch_list(args, generation)
            if args.list_only:
                print_menu(args.mode, found)
                return

            while True:
                print_menu(args.mode, found)
                if not found:
                    if preselected:
                        print("[INFO] Preselected row is kept; refreshing until a list is available.")
                        break
                    choice = read_choice(found, preselected)
                    if choice.lower() == "q":
                        return
                    break

                choice = read_choice(found, preselected)
                preselected = 0
                low = choice.lower()
                if low in ("q", "quit", "exit"):
                    return
                if low in ("r", "refresh", "reload"):
                    break
                try:
                    selected_index = int(choice)
                except ValueError:
                    print(f"[ERR] unsupported choice: {choice}")
                    continue

                result = None
                forwarder = None
                try:
                    result, forwarder = connect_selected(args, profile, found, selected_index, generation)
                    if result is None:
                        if args.once:
                            raise SystemExit(2)
                        print("[INFO] Choose another number from the same list, or r to refresh.")
                        continue
                    action = health_loop(args, result, forwarder)
                    if action == "quit":
                        return
                    if action == "menu":
                        break
                finally:
                    if forwarder is not None:
                        forwarder.stop()
                    stop_connector(args.base, timeout=10)
                if args.once:
                    return
    except KeyboardInterrupt:
        print("")
        print("[STOP] requested by user")
        stop_connector(args.base, timeout=10)


if __name__ == "__main__":
    main()
