#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

from jumpjump_native_proxy import (
    DEFAULT_ASSETS,
    DEFAULT_BASE,
    candidates,
    channels,
    endpoint,
    fetch_candidate_list,
    normalize_mode,
    nodes,
    purpose,
    stop_connector,
    try_start_candidate,
)


def channel_meta(profile, candidate):
    node = nodes(profile)[candidate["node_index"]]
    channel = channels(node)[candidate["channel_index"]]
    attrs = channel.get("nodeAttrs") or {}
    linkline = channel.get("linkline") or attrs.get("linkline") or {}
    host, port = endpoint(node, channel)
    if candidate.get("purpose") == "adpair":
        ad_channel = candidate.get("ad_channel") or {}
        ad_attrs = ad_channel.get("nodeAttrs") or {}
        ad_linkline = ad_channel.get("linkline") or ad_attrs.get("linkline") or {}
        return {
            "kind": "AD-PAIR",
            "purpose": "adpair",
            "id": candidate["id"],
            "normalId": candidate.get("normal_id"),
            "adId": candidate.get("ad_id"),
            "rankLatencyMs": candidate["latency_ms"],
            "adLatencyMs": candidate.get("ad_latency_ms"),
            "remote": f"{host}:{port}",
            "adRemote": f"{candidate.get('ad_host')}:{candidate.get('ad_port')}",
            "serverAddress": channel.get("serverAddress"),
            "serverName": channel.get("serverName"),
            "measureUrl": channel.get("measureUrl"),
            "adMeasureUrl": ad_channel.get("measureUrl"),
            "groupCode": attrs.get("groupCode"),
            "adGroupCode": ad_attrs.get("groupCode"),
            "groupId": attrs.get("groupId"),
            "linePurpose": "normal+ad",
            "lineType": f"{linkline.get('type')}+{ad_linkline.get('type')}",
            "country": linkline.get("country"),
            "region": linkline.get("region"),
            "idc": linkline.get("idc"),
            "isp": linkline.get("isp"),
            "tcpOutboundTag": channel.get("tcpOutboundTag"),
            "udpOutboundTag": channel.get("udpOutboundTag"),
            "adTcpOutboundTag": ad_channel.get("tcpOutboundTag"),
            "adUdpOutboundTag": ad_channel.get("udpOutboundTag"),
        }
    return {
        "kind": "AD-CONFIG" if purpose(channel) == "ad" else "APP-CONFIG",
        "purpose": purpose(channel),
        "id": candidate["id"],
        "rankLatencyMs": candidate["latency_ms"],
        "remote": f"{host}:{port}",
        "serverAddress": channel.get("serverAddress"),
        "serverName": channel.get("serverName"),
        "measureUrl": channel.get("measureUrl"),
        "groupCode": attrs.get("groupCode"),
        "groupId": attrs.get("groupId"),
        "linePurpose": channel.get("linePurpose") or linkline.get("linePurpose") or attrs.get("linePurpose"),
        "lineType": linkline.get("type"),
        "country": linkline.get("country"),
        "region": linkline.get("region"),
        "idc": linkline.get("idc"),
        "isp": linkline.get("isp"),
        "tcpOutboundTag": channel.get("tcpOutboundTag"),
        "udpOutboundTag": channel.get("udpOutboundTag"),
    }


def print_table(rows):
    headers = ["rank", "kind", "id", "remote", "latency", "group", "line", "country", "region", "outIp", "status"]
    print("\t".join(headers))
    for row in rows:
        print(
            "\t".join(
                str(row.get(key, ""))
                for key in ["rank", "kind", "id", "remote", "latency", "group", "line", "country", "region", "outIp", "status"]
            )
        )


def main():
    ap = argparse.ArgumentParser(description="List and optionally test live JumpJump APP/AD config candidates.")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--assets-dir", default=str(DEFAULT_ASSETS))
    ap.add_argument("--mode", choices=("ad", "ads", "adonly", "app", "normal", "smart", "all"), default="all")
    ap.add_argument("--group-code", default="autonewir")
    ap.add_argument("--refresh-country", default="IR")
    ap.add_argument("--refresh-lang", default="fa")
    ap.add_argument("--ad-media-platform", default="admob")
    ap.add_argument("--ping-timeout", type=float, default=1.8)
    ap.add_argument("--start-wait", type=int, default=15)
    ap.add_argument("--stability-probes", type=int, default=3)
    ap.add_argument("--stability-max-failures", type=int, default=0)
    ap.add_argument("--stability-delay-ms", type=int, default=700)
    ap.add_argument("--skip-measure", action="store_true")
    ap.add_argument("--test", action="store_true", help="start each candidate sequentially and print outbound IP")
    ap.add_argument("--max-test", type=int, default=0, help="0 means all candidates")
    ap.add_argument("--jsonl", action="store_true")
    args = ap.parse_args()
    args.requested_mode = args.mode
    args.mode = normalize_mode(args.mode)
    args.refresh = True

    profile, found = fetch_candidate_list(args, generation=1)
    rows = []
    limit = len(found) if not args.max_test else min(len(found), args.max_test)
    for index, candidate in enumerate(found, 1):
        meta = channel_meta(profile, candidate)
        row = {
            "rank": index,
            "kind": meta["kind"],
            "id": meta["id"],
            "remote": meta["remote"],
            "latency": meta["rankLatencyMs"],
            "group": meta.get("groupCode"),
            "line": meta.get("linePurpose"),
            "country": meta.get("country"),
            "region": meta.get("region"),
            "outIp": "",
            "status": "listed",
            "meta": meta,
        }
        if args.test and index <= limit:
            result, failure = try_start_candidate(args, profile, candidate, generation=1, rank=index)
            if result:
                row["outIp"] = result["public_ip"]
                row["status"] = "ok"
            else:
                row["status"] = "failed: " + failure[:300]
            stop_connector(args.base, timeout=10)
            time.sleep(0.5)
        rows.append(row)
        if args.jsonl:
            print(json.dumps(row, ensure_ascii=False, separators=(",", ":")))

    if not args.jsonl:
        print_table(rows)
        out = Path(__file__).resolve().parent / "runtime" / "scan_configs_last.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"SCAN_JSON={out}")


if __name__ == "__main__":
    main()
