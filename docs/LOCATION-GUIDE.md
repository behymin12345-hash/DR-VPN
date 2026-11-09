# راهنمای صفر تا صد — پنل + لوکیشن‌های تلگرام/خروج چند‌کشوری
# Zero-to-Hero: Panel + Tor/Psiphon Locations

> Persian guide below / [English summary at the end](#english-summary)

---

## فارسی — از صفر تا کاربر متصل

### پیش‌نیازها
| نیاز | توضیح |
|---|---|
| VPS | Ubuntu 20.04 / 22.04 / 24.04 — حداقل 1GB RAM (برای ۸ لوکیشن)، 2GB توصیه‌شده |
| دامنه | یک رکورد A → IP سرور (مثلاً `shop.example.ir`) |
| پورت‌های AWS Security Group | 8000، 443، 80، 2052، 2053، 8388 (همه TCP) |

### مرحله ۱ — نصب پنل (یک فرمان)

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/behymin12345-hash/DR-VPN/main/scripts/drvpn.sh)" @ install
```

ویزارد می‌پرسد:
```
Panel port [8000]:                ← Enter یا پورت دلخواه
Database: 1) SQLite ...           ← 1 (Enter)
SSL: 1) Domain with Let's Encrypt ← 1
Domain: shop.example.ir           ← دامنه‌ات
```
- گواهی SSL خودکار صادر می‌شود (پورت 80 باید باز باشد)
- در آخر **Setup Key** چاپ می‌شود — همان لحظه از داشبورد اکانت owner بساز

> ⚠️ اگر صفحه باز نشد: پورت‌های جدول بالا در Security Group باز نیستند.

### مرحله ۲ — نصب نود (روی همان سرور)

پنل خودش Xray اجرا نمی‌کند؛ نود لازم است. در همان ویزارد یا بعداً:

```bash
sudo drvpn install-node
```
- API Key را خالی بگذار (خودش می‌سازد) — یا همه سوالات را Enter بزن
- نود با Docker اجرا می‌شود و در پنل **connected** می‌شود

### مرحله ۳ — ساخت کانفیگ‌ها (یک‌بار)

از طریق API یا داشبورد: یک **Core Config** چند-پروتکلی (مثل VLESS Reality، VLESS WS، VMESS WS، Shadowsocks)، یک **گروه** شامل همه اینباند‌ها، و **Host** برای هر اینباند با آدرس دامنه‌ات. ساده‌ترین راه: نمونه آماده در [docs/NODE-SETUP.md](NODE-SETUP.md).

### مرحله ۴ — نصب tor-ml روی سرور (لوکیشن‌ها)

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/mrmarzx/Tor-ML-PRO/4.4/tor-ml.sh | tr -d '\r')" -- --install
sudo tor --mode weak                # برای سرورهای کم‌رم (1GB)
sudo tor --start T01 T03 T05 T19    # مثال: DE، NL، GB، IE
sudo tor --balancer-start           # بالانسر بهترین پینگ (:49000)
```

- ۶۰ لوکیشن Tor (پورت‌های 48180-48239) + ۲۸ Psiphon (49100-49127)
- رم هر لوکیشن در حالت weak ≈ ۳MB؛ روی 1GB حداکثر ~۸ لوکیشن
- پینگ هر لوکیشن: `sudo tor --ping T01`
- وضعیت همه: `sudo tor --json-status`

### مرحله ۵ — وصل‌کردن لوکیشن به اینباند (از خود پنل)

داشبورد → **Locations** → نود را انتخاب کن → کنار هر **اینباند** از منو، **لوکیشن** را انتخاب کن → **Apply & Restart Node**

پنل خودش در کانفیگ هسته‌ی آن نود:
1. یک outbound SOCKS به `127.0.0.1:<پورت لوکیشن>` می‌سازد
2. قانون routing «ترافیک این اینباند → خروج از این کشور» را اضافه می‌کند
3. نود را ری‌استارت می‌کند

**نتیجه:** کاربری که از آن اینباند وصل می‌شود، خروجش IP همان کشور است — لینک کاربر هیچ تغییری نمی‌کند.

### مرحله ۶ — ساخت کاربر

داشبورد → **Users → Create User** → گروه، سقف ترافیک، انقضا و **ضریب مصرف** (اختیاری: ضریب ۲ یعنی سهمیه ۲برابر سریع‌تر مصرف می‌شود) → لینک اشتراک آماده است.

---

## نکات مهم

- **پورت‌های لازم در Security Group:** 8000 (داشبورد)، 443، 2052، 2053، 8388 (پروکسی‌ها)، 80 (تمدید SSL). پورت‌های لوکیشن‌ها (48180 و …) **لازم نیست** باز شوند — فقط لوکال‌اند.
- **RAM:** روی سرور 1GB حداکثر ~۸ لوکیشن با `--mode weak`؛ لوکیشن‌های کم‌مصرف‌تر: DE، NL، GB، FR، CH
- **پینگ نمی‌دهد؟** لوکیشن باید استارت شده باشد (`tor --json-status` → running: true)، بوت‌استرپ Tor گاهی ۳۰-۶۰ ثانیه طول می‌کشد، `tor --log T01` را ببین
- **فرانسه/هر لوکیشن کار نمی‌کند؟** `tor --start T04` — ثبت و استارت دو چیز جدا هستند

---

## English summary

1. Install the panel: `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/behymin12345-hash/DR-VPN/main/scripts/drvpn.sh)" @ install` — wizard asks port, database and SSL domain; a Setup Key is printed to create the owner.
2. Install the node on the same (or another) server: `sudo drvpn install-node`.
3. Create a multi-protocol core config, a group containing all inbounds, and one Host per inbound pointing at your domain (see NODE-SETUP.md).
4. Install tor-ml (60 Tor + 28 Psiphon local SOCKS exits): the one-liner above, then `tor --mode weak && tor --start T01 T03 ... && tor --balancer-start`.
5. Dashboard → **Locations** → pick node → bind each inbound to a country → **Apply & Restart Node** (the panel generates the SOCKS outbound + routing rule in the node's core config — no SSH needed afterwards).
6. Create users — their subscription links stay identical; only the exit country changes.

Management: `tor --json-status` · `tor --ping T01` · `tor --log T01` · `tor --stop T01` · `tor --balancer-start` · `drvpn status`.
