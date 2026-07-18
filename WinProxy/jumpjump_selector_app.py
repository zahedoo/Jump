#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from jumpjump_native_proxy import ROOT, stop_connector
from jumpjump_select_proxy import main as selector_main


def post_json(base, path, timeout=2):
    req = Request(
        base + path,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        resp.read()


def test_sdk(base):
    try:
        post_json(base, "/api/stat", timeout=2)
        return True
    except Exception:
        return False


def start_sdk(sdk_exe, sdk_port):
    sdk_exe = Path(sdk_exe)
    if not sdk_exe.is_file():
        raise SystemExit(f"Missing native SDK: {sdk_exe}")

    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW

    try:
        return subprocess.Popen(
            [
                str(sdk_exe),
                "-http_addr",
                f"127.0.0.1:{sdk_port}",
                "-parent_process_id",
                str(os.getpid()),
            ],
            cwd=str(sdk_exe.parent),
            creationflags=creationflags,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) != 740:
            raise

        # xvpnsdk.exe can require elevation. CreateProcess returns WinError 740
        # in that case; Start-Process uses ShellExecute and lets Windows apply
        # the executable manifest/UAC policy.
        print("[APP] Native SDK requires elevation; starting it through Windows ShellExecute ...", flush=True)
        ps_script = (
            "$ErrorActionPreference='Stop'; "
            f"$exe={powershell_quote(str(sdk_exe))}; "
            f"$wd={powershell_quote(str(sdk_exe.parent))}; "
            f"$args=@('-http_addr','127.0.0.1:{int(sdk_port)}','-parent_process_id','{os.getpid()}'); "
            "Start-Process -WindowStyle Hidden -FilePath $exe -ArgumentList $args -WorkingDirectory $wd"
        )
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_script,
            ],
            check=True,
            creationflags=creationflags,
        )
        return None


def powershell_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def wait_sdk(base, seconds=20):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if test_sdk(base):
            return True
        time.sleep(0.4)
    return False


def stop_sdk_process(proc, sdk_port, seconds=8):
    """Stop the native SDK process for this GUI/selector instance.

    When xvpnsdk.exe is started normally, proc is a Popen object. If Windows
    forces ShellExecute/UAC, proc is None, so we stop only xvpnsdk.exe processes
    whose command line contains this selector's 127.0.0.1:<port> http address.
    """
    if proc is not None:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=seconds)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        except Exception:
            pass

    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW
    ps_script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$needle='127.0.0.1:{int(sdk_port)}'; "
        "Get-CimInstance Win32_Process -Filter \"name='xvpnsdk.exe'\" | "
        "Where-Object { $_.CommandLine -like \"*$needle*\" } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_script,
            ],
            timeout=seconds,
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def parse_launcher_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--sdk-port", type=int, default=8701)
    parser.add_argument("--sdk-exe", default=str(ROOT / "win_jump_install" / "bin" / "xvpnsdk.exe"))
    parser.add_argument("--keep-sdk", action="store_true")
    parser.add_argument("--no-refresh", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    known, remaining = parser.parse_known_args(argv)
    return known, remaining


def has_option(args, name):
    return any(arg == name or arg.startswith(name + "=") for arg in args)


def main():
    known, remaining = parse_launcher_args(sys.argv[1:])
    if known.help:
        print("JumpProxySelector.exe")
        print("")
        print("Default: starts native SDK, fetches live API, shows numbered config list, then connects selected row.")
        print("")
        print("Common examples:")
        print("  JumpProxySelector.exe --mode all")
        print("  JumpProxySelector.exe --mode normal")
        print("  JumpProxySelector.exe --mode ads")
        print("  JumpProxySelector.exe --mode all --list-only")
        print("  JumpProxySelector.exe --mode all --select 2")
        print("")
        print("Extra launcher options:")
        print("  --sdk-port 8701")
        print("  --sdk-exe C:\\path\\to\\xvpnsdk.exe")
        print("  --keep-sdk")
        print("  --no-refresh")
        return

    base = f"http://127.0.0.1:{known.sdk_port}"
    sdk_proc = None
    try:
        if not test_sdk(base):
            print(f"[APP] Starting native SDK on {base} ...", flush=True)
            sdk_proc = start_sdk(known.sdk_exe, known.sdk_port)
            if not wait_sdk(base):
                raise SystemExit(f"Native SDK did not become ready on {base}")
        else:
            print(f"[APP] Native SDK already running on {base}", flush=True)

        selector_argv = list(remaining)
        if not has_option(selector_argv, "--base"):
            selector_argv = ["--base", base] + selector_argv
        if not known.no_refresh and not has_option(selector_argv, "--refresh"):
            selector_argv = ["--refresh"] + selector_argv

        sys.argv = [sys.argv[0]] + selector_argv
        selector_main()
    finally:
        try:
            stop_connector(base, timeout=8)
        except Exception:
            pass
        if sdk_proc is not None and not known.keep_sdk:
            try:
                sdk_proc.terminate()
                sdk_proc.wait(timeout=5)
            except Exception:
                try:
                    sdk_proc.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
