#!/usr/bin/env python3
import argparse
import json
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from types import SimpleNamespace
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from jumpjump_native_proxy import (
    DEFAULT_ASSETS,
    DEFAULT_BASE,
    ROOT,
    RUNTIME,
    candidates,
    curl_status_ip,
    expose_public_port,
    normalize_mode,
    probe_socks_path,
    refresh_profile_from_api,
    stop_connector,
    try_start_candidate,
)
from jumpjump_select_proxy import candidate_kind, channel_line, format_ms, format_real, write_selection_list
from jumpjump_selector_app import start_sdk, stop_sdk_process, test_sdk, wait_sdk


PUBLIC_RELAY_HEALTH_URLS = ["http://ifconfig.me/ip"]


class NullWriter:
    def write(self, _text):
        return 0

    def flush(self):
        return None


if sys.stdout is None:
    sys.stdout = NullWriter()
if sys.stderr is None:
    sys.stderr = NullWriter()


class JumpProxyGui:
    def __init__(self, root):
        self.root = root
        self.root.title("Jump Proxy Selector")
        self.root.geometry("1180x760")
        self.root.minsize(980, 620)

        self.queue = queue.Queue()
        self.profile = None
        self.candidates = []
        self.result = None
        self.forwarder = None
        self.sdk_proc = None
        self.busy = False
        self.current_candidate = None
        self.auto_enabled = False
        self.auto_bad_keys = set()
        self.auto_stop = threading.Event()
        self.auto_thread = None
        self.auto_interval_seconds = 60
        self.auto_retry_timer = None
        self.auto_retry_seconds = 60
        self.auto_no_proxy_notified = False
        self.auto_last_found_key = ""
        self.health_stop = threading.Event()
        self.health_thread = None
        self.telegram = self._load_telegram_config()

        self.mode_var = tk.StringVar(value="all")
        self.public_port_var = tk.StringVar(value="10880")
        self.sdk_port_var = tk.StringVar(value="8701")
        self.allow_ip_var = tk.StringVar(value="")
        self.ping_timeout_var = tk.StringVar(value="1.8")
        self.start_wait_var = tk.StringVar(value="15")
        self.stability_probes_var = tk.StringVar(value="2")
        self.stability_failures_var = tk.StringVar(value="1")
        self.status_var = tk.StringVar(value="Idle")
        self.selected_var = tk.StringVar(value="No active config")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._drain_queue)

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.BOTH, expand=True)

        controls = ttk.LabelFrame(top, text="Connection settings", padding=10)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Mode").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
        self.mode_box = ttk.Combobox(
            controls,
            textvariable=self.mode_var,
            width=12,
            state="readonly",
            values=("all", "normal", "smart", "ads", "adonly"),
        )
        self.mode_box.grid(row=0, column=1, sticky=tk.W, padx=(0, 14))

        ttk.Label(controls, text="Public port").grid(row=0, column=2, sticky=tk.W, padx=(0, 6))
        ttk.Entry(controls, textvariable=self.public_port_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=(0, 14))

        ttk.Label(controls, text="SDK port").grid(row=0, column=4, sticky=tk.W, padx=(0, 6))
        ttk.Entry(controls, textvariable=self.sdk_port_var, width=10).grid(row=0, column=5, sticky=tk.W, padx=(0, 14))

        ttk.Label(controls, text="Allow IP").grid(row=0, column=6, sticky=tk.W, padx=(0, 6))
        ttk.Entry(controls, textvariable=self.allow_ip_var, width=20).grid(row=0, column=7, sticky=tk.W, padx=(0, 14))

        ttk.Label(controls, text="Ping timeout").grid(row=1, column=0, sticky=tk.W, pady=(8, 0), padx=(0, 6))
        ttk.Entry(controls, textvariable=self.ping_timeout_var, width=10).grid(row=1, column=1, sticky=tk.W, pady=(8, 0), padx=(0, 14))

        ttk.Label(controls, text="Start wait").grid(row=1, column=2, sticky=tk.W, pady=(8, 0), padx=(0, 6))
        ttk.Entry(controls, textvariable=self.start_wait_var, width=10).grid(row=1, column=3, sticky=tk.W, pady=(8, 0), padx=(0, 14))

        ttk.Label(controls, text="Startup probes").grid(row=1, column=4, sticky=tk.W, pady=(8, 0), padx=(0, 6))
        ttk.Entry(controls, textvariable=self.stability_probes_var, width=10).grid(row=1, column=5, sticky=tk.W, pady=(8, 0), padx=(0, 14))

        ttk.Label(controls, text="Allowed failures").grid(row=1, column=6, sticky=tk.W, pady=(8, 0), padx=(0, 6))
        ttk.Entry(controls, textvariable=self.stability_failures_var, width=10).grid(row=1, column=7, sticky=tk.W, pady=(8, 0), padx=(0, 14))

        buttons = ttk.Frame(top, padding=(0, 10, 0, 8))
        buttons.pack(fill=tk.X)

        self.refresh_btn = ttk.Button(buttons, text="Refresh list", command=self.refresh_list)
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.auto_btn = ttk.Button(buttons, text="Auto", command=self.auto_ads)
        self.auto_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.connect_btn = ttk.Button(buttons, text="Connect selected", command=self.connect_selected)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.disconnect_btn = ttk.Button(buttons, text="Disconnect", command=self.disconnect)
        self.disconnect_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.check_btn = ttk.Button(buttons, text="Health check", command=self.health_check_once)
        self.check_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(buttons, textvariable=self.status_var).pack(side=tk.RIGHT)

        table_frame = ttk.LabelFrame(top, text="Configs", padding=8)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = (
            "rank",
            "kind",
            "id",
            "remote",
            "ip",
            "real_ping",
            "tcp_ping",
            "ad_id",
            "ad_remote",
            "ad_ip",
            "ad_real_ping",
            "ad_tcp_ping",
            "region",
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
        headings = {
            "rank": "#",
            "kind": "Kind",
            "id": "ID",
            "remote": "Remote",
            "ip": "Ping IP",
            "real_ping": "Real Ping",
            "tcp_ping": "TCP",
            "ad_id": "AD ID",
            "ad_remote": "AD Remote",
            "ad_ip": "AD Ping IP",
            "ad_real_ping": "AD Real",
            "ad_tcp_ping": "AD TCP",
            "region": "Country / Region",
        }
        widths = {
            "rank": 45,
            "kind": 90,
            "id": 160,
            "remote": 175,
            "ip": 120,
            "real_ping": 95,
            "tcp_ping": 75,
            "ad_id": 130,
            "ad_remote": 175,
            "ad_ip": 120,
            "ad_real_ping": 95,
            "ad_tcp_ping": 75,
            "region": 210,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor=tk.W)

        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.tag_configure("ok", foreground="#0b6b2b")
        self.tree.tag_configure("nop", foreground="#8a5a00")
        self.tree.tag_configure("skip", foreground="#9b1c1c")

        bottom = ttk.Frame(top, padding=(0, 10, 0, 0))
        bottom.pack(fill=tk.BOTH)

        active = ttk.LabelFrame(bottom, text="Active", padding=8)
        active.pack(fill=tk.X)
        ttk.Label(active, textvariable=self.selected_var).pack(anchor=tk.W)

        logs = ttk.LabelFrame(bottom, text="Log", padding=8)
        logs.pack(fill=tk.BOTH, expand=False, pady=(8, 0))
        self.log_text = tk.Text(logs, height=9, wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(logs, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")
        logs.columnconfigure(0, weight=1)

    def log(self, text):
        stamp = time.strftime("%H:%M:%S")
        self.queue.put(("log", f"[{stamp}] {text}\n"))

    def set_status(self, text):
        self.queue.put(("status", text))

    def set_busy(self, busy):
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for btn in (self.refresh_btn, self.auto_btn, self.connect_btn, self.disconnect_btn, self.check_btn):
            btn.configure(state=state)
        if not busy:
            self.disconnect_btn.configure(state=tk.NORMAL)

    def _drain_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log_text.insert(tk.END, item[1])
                    self.log_text.see(tk.END)
                elif kind == "status":
                    self.status_var.set(item[1])
                elif kind == "rows":
                    self._set_rows(item[1])
                elif kind == "select":
                    iid = str(item[1])
                    if self.tree.exists(iid):
                        self.tree.selection_set(iid)
                        self.tree.focus(iid)
                        self.tree.see(iid)
                elif kind == "active":
                    self.selected_var.set(item[1])
                elif kind == "busy":
                    self.set_busy(item[1])
                elif kind == "error":
                    messagebox.showerror("Jump Proxy Selector", item[1])
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    def _set_rows(self, found):
        self.tree.delete(*self.tree.get_children())
        for index, candidate in enumerate(found, 1):
            main = channel_line(candidate, "channel")
            region = " ".join(x for x in (main.get("country"), main.get("region")) if x) or "-"
            values = (
                index,
                candidate_kind(candidate),
                candidate.get("id") or "",
                f"{candidate.get('host')}:{candidate.get('port')}",
                candidate.get("ping_ip") or candidate.get("ip") or "",
                format_real(candidate),
                format_ms(candidate.get("latency_ms")),
                candidate.get("ad_id") or "",
                f"{candidate.get('ad_host')}:{candidate.get('ad_port')}" if candidate.get("ad_host") else "",
                candidate.get("ad_ping_ip") or candidate.get("ad_ip") or "",
                format_real(candidate, "ad_") if candidate.get("ad_host") else "",
                format_ms(candidate.get("ad_latency_ms")) if candidate.get("ad_host") else "",
                region,
            )
            if self._candidate_block_reason(candidate):
                tag = "skip"
            else:
                tag = "ok" if candidate.get("real_ping_ms") is not None else "nop"
            self.tree.insert("", tk.END, iid=str(index), values=values, tags=(tag,))

    def _candidate_block_reason(self, candidate):
        if candidate.get("purpose") == "ad":
            return "ADS-RAW is an advertising bridge channel, not a full connector route"
        if candidate.get("latency_ms") is None:
            return "VPN TCP endpoint is not reachable; real ping alone is not enough to start the tunnel"
        return ""

    def _candidate_memory_key(self, candidate):
        return "|".join(
            str(candidate.get(k) or "")
            for k in ("purpose", "id", "host", "port", "ad_id")
        )

    def _load_telegram_config(self):
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
                config["botToken"] = str(
                    data.get("botToken") or data.get("token") or config["botToken"] or ""
                ).strip()
                config["chatId"] = str(
                    data.get("chatId")
                    or data.get("chat_id")
                    or data.get("userId")
                    or config["chatId"]
                    or ""
                ).strip()
            except Exception as exc:
                self.log(f"Telegram config ignored: {exc}")
        config["enabled"] = bool(config.get("enabled") and config.get("botToken") and config.get("chatId"))
        return config

    def _send_telegram(self, text):
        if not self.telegram.get("enabled"):
            return False
        payload = urlencode(
            {
                "chat_id": self.telegram["chatId"],
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{self.telegram['botToken']}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=12) as response:
                response.read()
            self.log("Telegram notification sent")
            return True
        except Exception as exc:
            first_error = str(exc)

        curl = shutil.which("curl.exe") or shutil.which("curl")
        if curl:
            try:
                process = subprocess.run(
                    [
                        curl,
                        "-sS",
                        "--max-time",
                        "15",
                        "-X",
                        "POST",
                        f"https://api.telegram.org/bot{self.telegram['botToken']}/sendMessage",
                        "-d",
                        f"chat_id={self.telegram['chatId']}",
                        "-d",
                        "disable_web_page_preview=true",
                        "--data-urlencode",
                        f"text={text}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if process.returncode == 0 and '"ok":true' in (process.stdout or ""):
                    self.log("Telegram notification sent")
                    return True
                fallback_error = (process.stderr or process.stdout or "").strip()[:300]
            except Exception as exc:
                fallback_error = str(exc)
        else:
            fallback_error = "curl not found"

        self.log(f"Telegram notification failed: urllib={first_error}; curl={fallback_error}")
        return False

    def _compact_failure_line(self, line):
        line = re.sub(r"\s+", " ", str(line or "")).strip()
        line = re.sub(r"curl: \(7\) Failed to connect to 127\.0\.0\.1 port \d+ after \d+ ms: Could not connect to server", "local_socks_closed", line)
        line = re.sub(r"curl: \(28\)[^|]+", "timeout", line)
        line = line.replace("curl: (52) Empty reply from server", "empty_reply")
        line = line.replace("cannot complete SOCKS5 connection", "socks5_connect_failed")
        line = line.replace("startup_probe_error=", "startup=")
        return line[:420]

    def _compact_no_proxy_reason(self, reason):
        text = str(reason or "")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        row_lines = [line for line in lines if line.startswith("row ")]
        source_lines = row_lines or lines[-4:]

        native_failed = sum(
            1
            for line in source_lines
            if "port_open=False" in line or "local_socks_closed" in self._compact_failure_line(line)
        )
        public_failed = sum(1 for line in source_lines if "public relay health failed" in line)
        socks_failed = sum(
            1
            for line in source_lines
            if "curl: (97)" in line or "cannot complete SOCKS5" in line or "socks5_connect_failed" in line
        )
        empty_failed = sum(1 for line in source_lines if "curl: (52)" in line or "Empty reply" in line)
        timeout_failed = sum(1 for line in source_lines if "curl: (28)" in line or "timed out" in line.lower())
        forbidden_failed = sum(
            1
            for line in source_lines
            if "status=403" in line or "forbidden" in line.lower() or "permission" in line.lower()
        )

        summary = [
            f"retry_after={self.auto_retry_seconds}s",
            f"tested_failures={len(source_lines)}",
            f"native_start_failed={native_failed}",
            f"public_relay_failed={public_failed}",
            f"socks5_failed={socks_failed}",
            f"empty_reply={empty_failed}",
            f"timeout={timeout_failed}",
            f"blocked_403={forbidden_failed}",
        ]
        if source_lines:
            summary.append("last_failures:")
            summary.extend(f"- {self._compact_failure_line(line)}" for line in source_lines[-3:])
        else:
            summary.append("reason=unknown")
        return "\n".join(summary)[:3600]

    def _notify_no_proxy(self, reason):
        if self.auto_no_proxy_notified:
            return
        self.auto_no_proxy_notified = True
        summary = self._compact_no_proxy_reason(reason)
        self._send_telegram(
            "JumpProxy Auto\n"
            "وضعیت: پروکسی خروجی سالم پیدا نشد.\n"
            "عملیات: refresh و تست تک‌به‌تک ادامه دارد.\n"
            f"جزئیات:\n{summary}"
        )

    def _notify_proxy_found(self, candidate=None, result=None):
        candidate = candidate or self.current_candidate
        result = result or self.result or {}
        key = self._candidate_memory_key(candidate) if candidate else ""
        if key and key == self.auto_last_found_key and not self.auto_no_proxy_notified:
            return
        self.auto_last_found_key = key
        self.auto_no_proxy_notified = False
        self._send_telegram(
            "JumpProxy Auto\n"
            "وضعیت: پروکسی خروجی پیدا شد و اتصال برقرار است.\n"
            f"نوع: {candidate_kind(candidate) if candidate else '-'}\n"
            f"ID: {candidate.get('id') if candidate else '-'}\n"
            f"Remote: {candidate.get('host') if candidate else '-'}:{candidate.get('port') if candidate else '-'}\n"
            f"IP خروجی: {result.get('public_ip') or '-'}"
        )

    def _cancel_auto_retry(self):
        timer = self.auto_retry_timer
        if timer is not None:
            timer.cancel()
            self.auto_retry_timer = None

    def _schedule_auto_retry(self, reason, delay=None):
        if not self.auto_enabled:
            return
        delay = self.auto_retry_seconds if delay is None else max(1, int(delay))
        self._cancel_auto_retry()
        self.log(f"Auto: retry scheduled in {delay}s ({reason})")

        def fire():
            if not self.auto_enabled:
                return
            if self.busy:
                self._schedule_auto_retry("worker busy", delay=10)
                return
            self.start_worker(self._auto_ads_worker)

        self.auto_retry_timer = threading.Timer(delay, fire)
        self.auto_retry_timer.daemon = True
        self.auto_retry_timer.start()

    def _int_var(self, var, name, minimum=0):
        try:
            value = int(str(var.get()).strip())
        except ValueError:
            raise ValueError(f"{name} must be an integer")
        if value < minimum:
            raise ValueError(f"{name} must be >= {minimum}")
        return value

    def _float_var(self, var, name, minimum=0.1):
        try:
            value = float(str(var.get()).strip())
        except ValueError:
            raise ValueError(f"{name} must be a number")
        if value < minimum:
            raise ValueError(f"{name} must be >= {minimum}")
        return value

    def base_url(self):
        return f"http://127.0.0.1:{self._int_var(self.sdk_port_var, 'SDK port', 1)}"

    def ensure_sdk(self):
        base = self.base_url()
        if test_sdk(base):
            self.log(f"Native SDK already running on {base}")
            return base

        sdk_port = self._int_var(self.sdk_port_var, "SDK port", 1)
        sdk_exe = str(ROOT / "win_jump_install" / "bin" / "xvpnsdk.exe")
        self.log(f"Starting native SDK on {base}")
        self.sdk_proc = start_sdk(sdk_exe, sdk_port)
        if not wait_sdk(base):
            raise RuntimeError(f"Native SDK did not become ready on {base}")
        return base

    def reset_sdk(self, reason="reset"):
        base = self.base_url()
        sdk_port = self._int_var(self.sdk_port_var, "SDK port", 1)
        self.log(f"Resetting native SDK ({reason}) ...")
        try:
            stop_connector(base, timeout=6)
        except Exception:
            pass
        stop_sdk_process(self.sdk_proc, sdk_port)
        self.sdk_proc = None
        deadline = time.time() + 6
        while time.time() < deadline:
            if not test_sdk(base):
                break
            time.sleep(0.25)

    def start_worker(self, func):
        if self.busy:
            return
        self.busy = True
        self.queue.put(("busy", True))
        t = threading.Thread(target=self._worker_wrapper, args=(func,), daemon=True)
        t.start()

    def _worker_wrapper(self, func):
        try:
            func()
        except Exception as exc:
            self.log(f"ERROR: {exc}")
            self.queue.put(("error", str(exc)))
        finally:
            self.queue.put(("busy", False))
            self.set_status("Idle")

    def refresh_list(self):
        self.start_worker(self._refresh_worker)

    def auto_ads(self):
        self.auto_enabled = True
        self.auto_bad_keys.clear()
        self.auto_no_proxy_notified = False
        self.auto_last_found_key = ""
        self._cancel_auto_retry()
        self.auto_stop.clear()
        self.mode_var.set("ads")
        self.start_worker(self._auto_ads_worker)

    def _auto_ads_worker(self):
        try:
            self._auto_ads_attempt()
        except Exception as exc:
            self.log(f"Auto: no output proxy found: {exc}")
            self._notify_no_proxy(exc)
            self._schedule_auto_retry("no output proxy found")

    def _auto_ads_attempt(self):
        self.set_status("Auto ADS: refreshing ...")
        self.log("Auto: switching to ADS mode and refreshing live list ...")
        self._refresh_worker()
        eligible = self._auto_eligible_indexes()
        if not eligible and self.auto_bad_keys:
            self.log("Auto: all ADS candidates are blacklisted; clearing 403 memory and retrying this list ...")
            self.auto_bad_keys.clear()
            eligible = self._auto_eligible_indexes()
        if not eligible:
            self._raise_no_auto_ads()
        chosen_zero_based = random.choice(eligible)
        chosen_index = chosen_zero_based + 1
        chosen = self.candidates[chosen_zero_based]
        self.queue.put(("select", chosen_index))
        self.log(
            f"Auto: randomly selected ADS row {chosen_index}: "
            f"id={chosen.get('id')} real={format_real(chosen)} tcp={format_ms(chosen.get('latency_ms'))}"
        )
        self._connect_worker(chosen_index, excluded_keys=set(self.auto_bad_keys), auto_only_ads=True)
        if self.result:
            self._notify_proxy_found(self.current_candidate, self.result)

    def _auto_eligible_indexes(self):
        return [
            index
            for index, candidate in enumerate(self.candidates)
            if candidate_kind(candidate) == "ADS-PAIR"
            and not self._candidate_block_reason(candidate)
            and self._candidate_memory_key(candidate) not in self.auto_bad_keys
        ]

    def _raise_no_auto_ads(self):
        raw_count = sum(1 for candidate in self.candidates if candidate_kind(candidate) == "ADS-RAW")
        pair_count = sum(1 for candidate in self.candidates if candidate_kind(candidate) == "ADS-PAIR")
        raise RuntimeError(
            "Auto ADS found no connectable ADS-PAIR rows. "
            f"pairs={pair_count}, raw_ads={raw_count}. Refresh again or wait for API to return full ad pairs."
        )

    def _refresh_worker(self):
        self.set_status("Refreshing ...")
        if self.result is not None or self.forwarder is not None:
            self.log("Active connection detected; disconnecting before refresh ...")
            self._disconnect_worker(silent=True, reset_sdk=True)
        else:
            self.reset_sdk("refresh")
        base = self.ensure_sdk()
        mode = normalize_mode(self.mode_var.get())
        self.log(f"Fetching live API list: mode={mode}")
        profile = refresh_profile_from_api(base, "autonewir", "IR", "fa", "admob")
        self.log("Measuring Real/ICMP/HTTP ping and TCP reachability for configs ...")
        found = candidates(profile, mode, self._float_var(self.ping_timeout_var, "Ping timeout"))
        self.profile = profile
        self.candidates = found
        write_selection_list(RUNTIME / "manual_selection_last.json", mode, found)
        self.queue.put(("rows", found))
        counts = {}
        for item in found:
            kind = candidate_kind(item)
            counts[kind] = counts.get(kind, 0) + 1
        count_text = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
        self.log(f"Loaded {len(found)} configs ({count_text}). Select a row and click Connect.")

    def connect_selected(self):
        try:
            index = self._selected_index()
        except Exception as exc:
            messagebox.showerror("Jump Proxy Selector", str(exc))
            return
        self.start_worker(lambda: self._connect_worker(index))

    def _selected_index(self):
        selected = self.tree.selection()
        if not selected:
            raise ValueError("Select a config row first")
        return int(selected[0])

    def _start_one_candidate(self, args, candidate, row_index):
        args.base = self.ensure_sdk()
        self.set_status(f"Connecting row {row_index} ...")
        self.log(
            f"Connecting row {row_index}: {candidate_kind(candidate)} id={candidate.get('id')} "
            f"real={format_real(candidate)} "
            f"tcp={format_ms(candidate.get('latency_ms'))}"
        )
        result, failure = try_start_candidate(args, self.profile, candidate, generation=1, rank=row_index)
        if result is None and (
            "port_open=False" in str(failure)
            or "Failed to connect to 127.0.0.1" in str(failure)
            or "Empty reply from server" in str(failure)
        ):
            self.log(f"First start failed with stale SDK symptom: {failure}")
            self.reset_sdk("retry after failed startup")
            args.base = self.ensure_sdk()
            self.log(f"Retrying row {row_index} after SDK reset ...")
            result, failure = try_start_candidate(args, self.profile, candidate, generation=1, rank=row_index)
        return result, failure

    def _connect_worker(self, index, excluded_keys=None, auto_only_ads=False):
        if not self.candidates:
            raise ValueError("Refresh the config list before connecting")
        if index < 1 or index > len(self.candidates):
            raise ValueError("Invalid selected row")

        self._disconnect_worker(silent=True, reset_sdk=True)
        mode = normalize_mode(self.mode_var.get())
        args = SimpleNamespace(
            base=self.base_url(),
            assets_dir=str(DEFAULT_ASSETS),
            skip_measure=False,
            start_wait=self._int_var(self.start_wait_var, "Start wait", 1),
            stability_probes=self._int_var(self.stability_probes_var, "Startup probes", 1),
            stability_max_failures=self._int_var(self.stability_failures_var, "Allowed failures", 0),
            stability_delay_ms=700,
            mode=mode,
            refresh=True,
        )

        ordered_indexes = [index - 1] + [i for i in range(len(self.candidates)) if i != index - 1]
        connectable_indexes = []
        excluded_keys = excluded_keys or set()
        for candidate_index in ordered_indexes:
            candidate_for_filter = self.candidates[candidate_index]
            if auto_only_ads and candidate_kind(candidate_for_filter) != "ADS-PAIR":
                self.log(f"Skipping row {candidate_index + 1}: Auto only selects ADS-PAIR full routes")
                continue
            if self._candidate_memory_key(candidate_for_filter) in excluded_keys:
                self.log(f"Skipping row {candidate_index + 1}: blacklisted after previous 403")
                continue
            reason = self._candidate_block_reason(candidate_for_filter)
            if reason:
                self.log(f"Skipping row {candidate_index + 1}: {reason}")
                continue
            connectable_indexes.append(candidate_index)
        if not connectable_indexes:
            if auto_only_ads:
                raise RuntimeError("No connectable ADS-PAIR rows after blacklist/filtering.")
            raise RuntimeError("No connectable rows. Need NORMAL+AD/ADS-PAIR with reachable TCP endpoint.")

        failures = []
        result = None
        candidate = None
        chosen_index = index
        public_port = self._int_var(self.public_port_var, "Public port", 0)
        self.forwarder = None
        for attempt, candidate_index in enumerate(connectable_indexes, 1):
            candidate = self.candidates[candidate_index]
            chosen_index = candidate_index + 1
            if attempt > 1:
                self.log(f"Auto fallback: trying row {chosen_index} after previous startup failure ...")
                self.reset_sdk("fallback candidate")
            result, failure = self._start_one_candidate(args, candidate, chosen_index)
            if result is not None:
                if public_port > 0:
                    validation_forwarder = None
                    try:
                        validation_forwarder = expose_public_port(
                            public_port,
                            result["socks_port"],
                            "0.0.0.0",
                            self.allow_ip_var.get().strip(),
                            8,
                            8,
                            2,
                            262144,
                            262144,
                        )
                        self.log(f"Public SOCKS5 listening on 0.0.0.0:{public_port}")
                        public_check = curl_status_ip(
                            public_port,
                            "127.0.0.1",
                            urls=PUBLIC_RELAY_HEALTH_URLS,
                        )
                        if not public_check.get("ok"):
                            if public_check.get("forbidden") and auto_only_ads:
                                self.auto_bad_keys.add(self._candidate_memory_key(candidate))
                            public_error = (
                                f"public relay health failed url={public_check.get('url') or PUBLIC_RELAY_HEALTH_URLS[0]} "
                                f"status={public_check.get('status')} error={public_check.get('error')}"
                            )
                            failures.append(
                                f"row {chosen_index} {candidate_kind(candidate)} id={candidate.get('id')}: {public_error}"
                            )
                            self.log(f"Start failed: {failures[-1]}")
                            try:
                                validation_forwarder.stop()
                            except Exception:
                                pass
                            validation_forwarder = None
                            stop_connector(args.base, timeout=8)
                            result = None
                            continue
                        self.forwarder = validation_forwarder
                        self.log(
                            f"Public relay health OK: ip={public_check.get('ip')} "
                            f"url={public_check.get('url')}"
                        )
                    except Exception as exc:
                        failures.append(
                            f"row {chosen_index} {candidate_kind(candidate)} id={candidate.get('id')}: "
                            f"public relay start/check failed: {exc}"
                        )
                        self.log(f"Start failed: {failures[-1]}")
                        if validation_forwarder is not None:
                            try:
                                validation_forwarder.stop()
                            except Exception:
                                pass
                        stop_connector(args.base, timeout=8)
                        result = None
                        continue
                break
            failures.append(f"row {chosen_index} {candidate_kind(candidate)} id={candidate.get('id')}: {failure}")
            self.log(f"Start failed: {failures[-1]}")

        if result is None or candidate is None:
            raise RuntimeError(
                "No listed config passed startup health. Last errors:\n" + "\n".join(failures[-4:])
            )

        self.result = result
        self.current_candidate = candidate
        active = (
            f"Active: row {chosen_index} | {candidate_kind(candidate)} | id={candidate.get('id')} | "
            f"local=127.0.0.1:{result['socks_port']} | public_port={public_port} | "
            f"ip={result['public_ip']}"
        )
        self.queue.put(("active", active))
        self.log(active)
        self.set_status("Connected")
        if self.auto_enabled:
            self._start_auto_watchdog()

    def _start_auto_watchdog(self):
        if self.auto_thread is not None and self.auto_thread.is_alive():
            return
        self.auto_stop.clear()
        self.auto_thread = threading.Thread(target=self._auto_watchdog_loop, daemon=True)
        self.auto_thread.start()
        self.log(f"Auto watchdog enabled: checking IP/status every {self.auto_interval_seconds}s")

    def _auto_watchdog_loop(self):
        while not self.auto_stop.wait(self.auto_interval_seconds):
            if not self.auto_enabled:
                return
            if self.busy or not self.result:
                continue
            public_port = self._int_var(self.public_port_var, "Public port", 0)
            if public_port > 0:
                check = curl_status_ip(public_port, "127.0.0.1", urls=PUBLIC_RELAY_HEALTH_URLS)
                health_path = "public_relay"
            else:
                check = curl_status_ip(self.result["socks_port"], "127.0.0.1")
                health_path = "native_socks"
            if check.get("ok"):
                self.log(
                    f"Auto watchdog OK ({health_path}): ip={check.get('ip')} "
                    f"status={check.get('status')} url={check.get('url')}"
                )
                self.queue.put(("active", self.selected_var.get() + f" | watchdog_ip={check.get('ip')}"))
                continue

            candidate = self.current_candidate
            if check.get("forbidden") and candidate:
                key = self._candidate_memory_key(candidate)
                self.auto_bad_keys.add(key)
                self.log(
                    f"Auto watchdog got 403; blacklisting current config id={candidate.get('id')} "
                    f"bad_count={len(self.auto_bad_keys)}"
                )
            else:
                self.log(
                    "Auto watchdog failed; rotating config: "
                    f"status={check.get('status')} error={check.get('error')}"
                )

            if not self.busy:
                self.start_worker(self._auto_ads_worker)

    def health_check_once(self):
        self.start_worker(self._health_worker)

    def _health_worker(self):
        if not self.result:
            raise ValueError("No active config")
        self.set_status("Health check ...")
        public_port = self._int_var(self.public_port_var, "Public port", 0)
        if public_port > 0:
            check = curl_status_ip(public_port, "127.0.0.1", urls=PUBLIC_RELAY_HEALTH_URLS)
            if check.get("ok"):
                self.log(f"Health OK public_relay: ip={check.get('ip')} via {check.get('url')}")
                self.queue.put(("active", self.selected_var.get() + f" | last_health_ip={check.get('ip')}"))
            else:
                self.log(
                    "Health FAIL public_relay: "
                    f"status={check.get('status')} error={check.get('error')}"
                )
            return
        ok, out, checked_url, _successes, failures = probe_socks_path(
            self.result["socks_port"],
            "127.0.0.1",
            2,
            1,
            500,
            "GUI_HEALTH",
        )
        if ok and out:
            self.log(f"Health OK: ip={out} via {checked_url}")
            self.queue.put(("active", self.selected_var.get() + f" | last_health_ip={out}"))
        else:
            err = " | ".join(f"{f['url']}: {f['error']}" for f in failures[-3:])
            self.log(f"Health FAIL: {err}")

    def disconnect(self):
        self.start_worker(lambda: self._disconnect_worker(silent=False, stop_auto=True))

    def _disconnect_worker(self, silent=False, reset_sdk=False, stop_auto=False):
        if stop_auto:
            self.auto_enabled = False
            self.auto_stop.set()
            self._cancel_auto_retry()
        if self.forwarder is not None:
            try:
                self.forwarder.stop()
            except Exception:
                pass
            self.forwarder = None
        try:
            stop_connector(self.base_url(), timeout=8)
        except Exception:
            pass
        if reset_sdk:
            self.reset_sdk("disconnect")
        self.result = None
        self.current_candidate = None
        self.queue.put(("active", "No active config"))
        if not silent:
            self.log("Disconnected")

    def on_close(self):
        try:
            self._disconnect_worker(silent=True, reset_sdk=True, stop_auto=True)
        except Exception:
            pass
        self.root.destroy()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.smoke_test:
        print("GUI imports OK")
        return
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.1)
    except Exception:
        pass
    JumpProxyGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
