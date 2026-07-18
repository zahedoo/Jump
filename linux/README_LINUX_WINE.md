# JumpProxy Linux/Wine

This package runs the same XVPN Windows SDK on Ubuntu through Wine. It does not use Xray or sing-box as a replacement core.

## Architecture

```text
Ubuntu Python runner
  -> Wine xvpnsdk.exe on 127.0.0.1:8701
  -> XVPN SDK local SOCKS on 127.0.0.1:55412
  -> Python public SOCKS relay on 0.0.0.0:10880
```

## Install on Ubuntu

Copy/unzip the package to a stable path, preferably:

```bash
sudo mkdir -p /opt/JumpProxyLinuxWine
sudo cp -a JumpProxyLinuxWine/* /opt/JumpProxyLinuxWine/
sudo chown -R "$USER:$USER" /opt/JumpProxyLinuxWine
cd /opt/JumpProxyLinuxWine
```

Install dependencies:

```bash
bash linux/install_ubuntu.sh
```

## Run manually

```bash
cd /opt/JumpProxyLinuxWine
./linux/run_xvpn_wine_proxy.sh --public-port 10880 --mode ad
```

Expected logs:

```text
XVPN SDK ready.
PUBLIC_HEALTH_OK ip=...
PUBLIC_SOCKS5=0.0.0.0:10880
WATCHDOG=enabled ... target=public_relay:127.0.0.1:10880
```

Test locally:

```bash
./linux/test_public_proxy.sh 127.0.0.1 10880
```

Test from another machine:

```bash
curl --socks5-hostname SERVER_IP:10880 http://ifconfig.me/ip
```

## Run with systemd

```bash
cd /opt/JumpProxyLinuxWine
sudo linux/install_systemd_service.sh
sudo systemctl start jump-proxy-xvpn
journalctl -u jump-proxy-xvpn -f
```

## Common environment overrides

```bash
MODE=normal PUBLIC_PORT=10880 ./linux/run_xvpn_wine_proxy.sh
MODE=ad PUBLIC_MAX_CONNECTIONS=16 ./linux/run_xvpn_wine_proxy.sh
PUBLIC_HEALTH_URL=http://ifconfig.me/ip ./linux/run_xvpn_wine_proxy.sh
```

## Firewall

The Python relay listens on `0.0.0.0:10880`. Open the port only if needed:

```bash
sudo ufw allow 10880/tcp
```

If the server is on a cloud provider, also open TCP `10880` in the provider security group.

## Notes

- This package keeps the XVPN SDK core. It does not swap to Xray/sing-box.
- `telegram_config.json` is read from the package root, or use `JUMP_TELEGRAM_BOT_TOKEN` and `JUMP_TELEGRAM_CHAT_ID` environment variables.
- The dedicated Wine prefix is `.wine-xvpn` inside this package by default.
- If Wine cannot run `xvpnsdk.exe`, the log is written to `WinProxy/runtime/xvpnsdk-wine.log`.

