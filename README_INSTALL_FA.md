# راهنمای نصب حرفه‌ای JumpProxy روی Linux

این راهنما برای Ubuntu، Debian و Linux Mint است.

## نصب سریع

اگر از فایل ZIP نهایی استفاده می‌کنی:

```bash
sudo mkdir -p /opt/JumpProxyLinuxWine
sudo unzip JumpProxyLinuxFinal_*.zip -d /opt/JumpProxyLinuxWine
cd /opt/JumpProxyLinuxWine
sudo bash install.sh --allow-firewall
```

بعد از نصب، سرویس خودش enable و restart می‌شود.

تست:

```bash
curl --socks5-hostname 127.0.0.1:10880 http://ifconfig.me/ip
```

تست از بیرون:

```bash
curl --socks5-hostname SERVER_IP:10880 http://ifconfig.me/ip
```

## نصب از GitHub

ریپازیتوری عمومی باینری‌های خصوصی مثل `xvpnsdk.exe` و DLLها را ندارد. بعد از clone باید runtime خصوصی را کپی کنی:

```bash
git clone https://github.com/zahedoo/Jump.git
cd Jump

mkdir -p win_jump_install/bin/assets
cp /path/to/xvpnsdk.exe win_jump_install/bin/
cp /path/to/iphlpapi.dll win_jump_install/bin/
cp /path/to/fwpuclnt.dll win_jump_install/bin/
cp /path/to/wintun.dll win_jump_install/bin/
cp /path/to/geoip.dat win_jump_install/bin/assets/
cp /path/to/geosite.dat win_jump_install/bin/assets/

sudo bash install.sh --allow-firewall
```

## دستورهای مهم

وضعیت:

```bash
sudo bash /opt/JumpProxyLinuxWine/install.sh --status
```

لاگ زنده:

```bash
sudo bash /opt/JumpProxyLinuxWine/install.sh --logs
```

تست:

```bash
sudo bash /opt/JumpProxyLinuxWine/install.sh --test
```

ری‌استارت:

```bash
sudo bash /opt/JumpProxyLinuxWine/install.sh --restart
```

حذف فقط سرویس:

```bash
sudo bash /opt/JumpProxyLinuxWine/install.sh --uninstall -y
```

حذف کامل سرویس، فایل تنظیمات و پوشه نصب:

```bash
sudo bash /opt/JumpProxyLinuxWine/install.sh --uninstall --purge -y
```

## نصب با پورت یا مسیر دلخواه

```bash
sudo bash install.sh \
  --install-dir /opt/JumpProxyLinuxWine \
  --port 10880 \
  --listen 0.0.0.0 \
  --mode ad \
  --allow-firewall
```

اگر نمی‌خواهی سرویس بعد از نصب start شود:

```bash
sudo bash install.sh --no-start --no-test
```

اگر dependencyها قبلاً نصب شده‌اند:

```bash
sudo bash install.sh --skip-deps
```

## فایل تنظیمات سرویس

Installer تنظیمات را اینجا می‌نویسد:

```text
/etc/jumpproxy.env
```

مقادیر مهم:

```text
PUBLIC_PORT=10880
PUBLIC_LISTEN=0.0.0.0
MODE=ad
DIRECT_FALLBACK=1
PUBLIC_MAX_CONNECTIONS=16
PUBLIC_CLIENT_FAILOVER_ATTEMPTS=4
PUBLIC_CLIENT_FAILOVER_WAIT_SECONDS=120
PUBLIC_CONNECT_FAILURES_BEFORE_ROTATE=1
HEALTH_INTERVAL=120
HEALTH_FAILURES=5
```

بعد از تغییر:

```bash
sudo systemctl daemon-reload
sudo systemctl restart jumpproxy
```

## رفتار پایداری و fallback

این نسخه طوری تنظیم شده که public SOCKS همیشه تا حد ممکن جواب بدهد:

- اگر کانفیگ سالم باشد، خروجی از کانفیگ می‌رود.
- اگر کانفیگ لحظه‌ای خراب شود، درخواست client نگه داشته می‌شود و بعد از rotate دوباره retry می‌شود.
- اگر هیچ کانفیگ سالمی پیدا نشود، request مستقیم از IP خود سرور خارج می‌شود.
- همزمان watchdog همچنان live API را refresh می‌کند و دنبال کانفیگ سالم می‌گردد.

مقادیر مربوط:

```text
DIRECT_FALLBACK=1
PUBLIC_CONNECT_FAILURES_BEFORE_ROTATE=1
PUBLIC_CLIENT_FAILOVER_ATTEMPTS=4
PUBLIC_CLIENT_FAILOVER_WAIT_SECONDS=120
```

## مسیرهای مهم

```text
/opt/JumpProxyLinuxWine/
/opt/JumpProxyLinuxWine/WinProxy/runtime/
/etc/jumpproxy.env
/etc/systemd/system/jumpproxy.service
```

## عیب‌یابی سریع

بررسی سرویس:

```bash
systemctl status jumpproxy --no-pager
```

بررسی پورت‌ها:

```bash
ss -lntp | grep -E ':(10880|55412|8701)\b'
```

باید چیزی شبیه این ببینی:

```text
0.0.0.0:10880
127.0.0.1:55412
127.0.0.1:8701
```

بررسی لاگ:

```bash
journalctl -u jumpproxy -n 200 --no-pager
```

اگر بیرون از سرور وصل نمی‌شود:

```bash
sudo ufw status
sudo ufw allow 10880/tcp
```

و در پنل provider/security group هم TCP port `10880` را باز کن.

## پیام‌های لاگ مهم

```text
PUBLIC_FORWARDER_INITIAL_TARGET=direct_fallback
PUBLIC_DIRECT_FALLBACK=True
PUBLIC_DIRECT_FALLBACK dest=...
PUBLIC_CONNECT_FAIL ...
PUBLIC_HEALTH_OK path=native_socks_strict ...
WATCHDOG=enabled interval=120s failures=5 target=native_socks...
```

اگر `PUBLIC_DIRECT_FALLBACK` دیدی یعنی موقتاً از IP خود سرور خارج شده تا کانفیگ سالم جایگزین شود.
