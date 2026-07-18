# Jump

Linux runtime and proxy manager for the JumpJump service.

This repository contains the public-safe source code, Linux service scripts, GUI/controller code, Wine compatibility shims, health-check logic, auto reconnect/watchdog flow, and Telegram notification integration.

Runtime binaries are intentionally not included in this public repository. Place your licensed/private runtime files locally under:

```text
win_jump_install/bin/
```

Required runtime layout:

```text
win_jump_install/bin/xvpnsdk.exe
win_jump_install/bin/iphlpapi.dll
win_jump_install/bin/fwpuclnt.dll
win_jump_install/bin/wintun.dll
win_jump_install/bin/assets/geoip.dat
win_jump_install/bin/assets/geosite.dat
```

## Features

- Live API profile refresh
- AD / normal / all mode candidate selection
- SOCKS5 public relay
- Linux/Wine runner for the native SDK
- Auto watchdog and reconnect
- Startup and public health probes
- Blacklist/rotation when a config fails
- Telegram notifications for failure and recovery
- systemd service mode

## Install on Ubuntu/Debian/Linux Mint

```bash
sudo mkdir -p /opt/JumpProxyLinuxWine
sudo cp -a . /opt/JumpProxyLinuxWine/
cd /opt/JumpProxyLinuxWine
sudo bash install.sh
```

Copy the private runtime files into:

```bash
sudo mkdir -p /opt/JumpProxyLinuxWine/win_jump_install/bin/assets
sudo cp xvpnsdk.exe iphlpapi.dll fwpuclnt.dll wintun.dll /opt/JumpProxyLinuxWine/win_jump_install/bin/
sudo cp geoip.dat geosite.dat /opt/JumpProxyLinuxWine/win_jump_install/bin/assets/
```

Start the service:

```bash
sudo systemctl restart jumpproxy
sudo systemctl status jumpproxy
```

Follow logs:

```bash
sudo journalctl -u jumpproxy -f
```

## Manual run

```bash
sudo bash run.sh
```

Default public SOCKS5 port:

```text
0.0.0.0:10880
```

Local test:

```bash
curl --socks5-hostname 127.0.0.1:10880 http://ifconfig.me/ip
```

External test:

```bash
curl --socks5-hostname SERVER_IP:10880 http://ifconfig.me/ip
```

## Telegram notification

Create `telegram_config.json` from the example:

```bash
cp telegram_config.example.json telegram_config.json
```

Then fill:

```json
{
  "bot_token": "YOUR_BOT_TOKEN",
  "chat_id": "YOUR_CHAT_ID"
}
```

Do not commit `telegram_config.json`.

You can also use environment variables:

```bash
export JUMP_TELEGRAM_BOT_TOKEN="..."
export JUMP_TELEGRAM_CHAT_ID="..."
```

## Service behavior

The service keeps the proxy alive with this flow:

1. Fetch fresh API data.
2. Build candidate list for selected mode.
3. Start native connector through Wine.
4. Open local SOCKS5.
5. Expose public SOCKS5 relay.
6. Check outbound IP and HTTP status.
7. If the config fails, blacklist it and rotate.
8. If all configs fail, clear blacklist and refresh live API data again.

Failure conditions include:

- HTTP 400/401/403/407/429
- timeout
- empty response
- SOCKS connection failure
- response body containing forbidden/access denied errors

## Notes

- This repository does not include credentials, server IPs, Telegram secrets, logs, runtime cache, or private binary artifacts.
- Public repositories should not include proprietary SDK binaries unless you have explicit permission to redistribute them.
