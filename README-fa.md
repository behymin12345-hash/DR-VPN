<p align="center">
  <a href="#" target="_blank" rel="noopener noreferrer">
    <img width="160" height="160" src="assets/branding/logo.png" alt="لوگوی DR-VPN">
  </a>
</p>

<h1 align="center">⚡ DR-VPN</h1>

<p align="center">
    <strong>پنل مدیریت پروکسی سبک و مستقل</strong>
</p>

<p align="center">
  <a href="./README.md">🇬🇧 English</a>
</p>

---

> [!WARNING]
> **DR-VPN در نسخه اولیه (v0.1.1) و در حال توسعه فعال است.** پنل، نصب‌کننده
> یک‌فرمانی و داشبورد کاملاً اجرایی هستند (کل مجموعه تست پاس می‌شود؛ نصب‌کننده
> به‌صورت end-to-end روی اوبونتو ۲۴.۰۴ تازه تست شد). هنوز در نقشه راه:
> بنچمارک منابع، ماژول نمایندگی (اسپانسری) و بازطراحی کامل داشبورد.
> وضعیت دقیق را در [نقشه راه](#️-نقشه-راه) ببینید.

## 📖 DR-VPN چیست؟

DR-VPN یک پنل مدیریت پروکسی سبک و self-host است برای اجرا و مدیریت صدها اکانت
پروکسی از طریق یک داشبورد وب تمیز، یک REST API کامل و خط فرمان. این پنل
کانفیگ‌های [Xray-core](https://github.com/XTLS/Xray-core) را مدیریت می‌کند و با
Node های راه‌دور Xray کار می‌کند.

DR-VPN یک فورک از [PasarGuard](https://github.com/PasarGuard/panel) (AGPL-3.0)
است که خود آن هم برگرفته از [Marzban](https://github.com/Gozargah/Marzban) می‌باشد.
اهداف DR-VPN: هویت بصری کاملاً مستقل، سیستم نمایندگی (اسپانسری)، داشبورد
تمیز و تمام‌انگلیسی، و کاهش مصرف منابع روی سرورهای کوچک. تمام اعتبار کد پایه
متعلق به پروژه‌های upstream است — جزئیات در [NOTICE.md](NOTICE.md).

## ✨ امکانات

**🌐 رابط وب و API**
- داشبورد **وب UI** (React) با تم تاریک/روشن
- بک‌اند **REST API** کامل (با OpenAPI schema)
- پشتیبانی **Multi-Node** برای توزیع زیرساخت

**🔐 پروتکل‌ها و امنیت**
- پشتیبانی از **Vmess**، **VLESS**، **Trojan**، **Shadowsocks**، **WireGuard** و **Hysteria2**
- پشتیبانی **TLS** و **REALITY**
- **چند پروتکل** برای یک کاربر

**👥 مدیریت کاربران**
- **چند کاربر** روی یک اینباند و **چند اینباند** روی یک پورت (با fallback)
- محدودیت **ترافیک** و **تاریخ انقضا**، محدودیت دوره‌ای (روزانه، هفتگی و ...)
- محدودیت **HWID/دستگاه**
- **چند ادمین** با **RBAC** (مجوزهای اسکوپ‌دار و مالکیت کاربر برای هر ادمین)

**🔗 اشتراک و اشتراک‌گذاری**
- لینک اشتراک سازگار با **V2ray**، **Clash**، **ClashMeta**، **sing-box** و بیشتر
- تولید خودکار **لینک اشتراک‌گذاری** و **QR کد**
- آمار ترافیک و مانیتورینگ

**🛠️ ابزارها و شخصی‌سازی**
- کانفیگ Xray قابل‌سفارشی‌سازی با اعتبارسنجی
- **ربات تلگرام** یکپارچه (اختیاری)
- **CLI** برای کلیدهای نصب و مدیریت
- رابط **چندزبانه** (English / فارسی / Русский / 中文) با پشتیبانی کامل RTL

## 🖼️ اسکرین‌شات‌ها

| | |
|---|---|
| ![ورود](assets/screenshots/01-login.png) | ![داشبورد](assets/screenshots/02-dashboard.png) |
| ![کاربران](assets/screenshots/03-users.png) | ![نودها](assets/screenshots/04-nodes.png) |

## 🚀 نصب

### یک فرمان (توصیه‌شده)

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/behymin12345-hash/DR-VPN/main/scripts/drvpn.sh)" @ install
```

نصب‌کننده به‌صورت تعاملی می‌پرسد (پورت، دیتابیس، SSL/دامین — ویزارد به سبک
پاسارگارد) و سپس اوبونتو ۲۰.۰۴/۲۲.۰۴/۲۴.۰۴ را تشخیص می‌دهد، uv + Python 3.14 را
نصب می‌کند، داشبورد از پیش ساخته‌شده را منتشر می‌کند، مهاجرت‌ها را اجرا می‌کند،
سرویس systemd با استارت خودکار می‌سازد، کلید یک‌بارمصرف owner را چاپ می‌کند و
CLI مدیریتی `drvpn` را در اختیار می‌گذارد:

```bash
drvpn status                  # وضعیت سرویس + health
drvpn ssl                     # افزودن/تعویض/حذف دامنه و SSL بعد از نصب
drvpn cli generate-temp-key
drvpn backup                  # آرشیو دیتابیس + کانفیگ
drvpn update                  # بکاپ -> pull -> مهاجرت -> ری‌استارت
drvpn help
```

گزینه‌های نصب (جواب ویزارد را از قبل می‌دهند): `--port`، `--ssl-domain example.com` (نیازمند پورت 80)،
`--no-ssl`، `--database sqlite|postgresql|mysql`، `--db-url`، `--version`، `--yes`
(کاملاً بی‌صدا برای اتوماسیون). بدون SSL پنل فقط روی localhost سرو می‌شود
(پیش‌فرض امنیتی) — دامنه را بعداً با `drvpn ssl` اضافه کنید.

<details>
<summary>نصب دستی (توسعه)</summary>

پیش‌نیاز: لینوکس x86_64 یا ویندوز برای توسعه، به‌علاوه [uv](https://docs.astral.sh/uv/).

```bash
# ۱. دریافت کد
git clone https://github.com/behymin12345-hash/DR-VPN.git
cd DR-VPN

# ۲. نصب Python 3.14 + وابستگی‌ها (uv همه‌چیز را مدیریت می‌کند)
uv sync

# ۳. پیکربندی
cp .env.example .env   # سپس تنظیمات را ویرایش کنید

# ۴. اجرای پنل
uv run python main.py

# ۵. در ترمینال دیگر، یک کلید نصب یک‌بارمصرف برای اکانت owner بسازید
uv run python drvpn-cli.py generate-temp-key
```

سپس داشبورد را باز کنید و با کلید setup، اکانت owner را بسازید. بدون گواهی SSL
پنل فقط روی localhost سرو می‌شود — برای اولین دسترسی از گواهی SSL یا SSH port
forwarding استفاده کنید:

</details>

```bash
ssh -L 8000:localhost:8000 user@serverip
# سپس http://localhost:8000/dashboard/ را باز کنید
```

جزئیات، متغیرهای محیطی و نکات systemd در [INSTALL.md](INSTALL.md).

### داکر

```bash
# دریافت تصویر منتشرشده (ساخت خودکار توسط CI)
docker pull ghcr.io/behymin12345-hash/dr-vpn:v0.1.0

# یا ساخت از سورس
docker build -t dr-vpn .

docker run -d --name dr-vpn --network host -v /var/lib/drvpn:/var/lib/drvpn --env-file .env dr-vpn
```

## 📚 مستندات

- مستندات کامل (upstream — با عملکرد فعلی منطبق است): [docs.pasarguard.org](https://docs.pasarguard.org)
- تحلیل معماری این فورک: [docs/ARCHITECTURE-REPORT.md](docs/ARCHITECTURE-REPORT.md)

## 🗺️ نقشه راه

| مرحله | شرح | وضعیت |
|---|---|---|
| ۱ | تحلیل معماری مخزن | ✅ انجام شد |
| ۲ | برندینگ و هویت DR-VPN | ✅ انجام شد |
| ۳ | baseline اجرایی: رفع خطاهای سینتکس، تست سبز، اولین انتشار | ✅ انجام شد |
| ۴ | نصب‌کننده یک‌فرمانی (systemd، بکاپ/ری‌استور/آپدیت) | ✅ انجام شد |
| ۵ | بهینه‌سازی عملکرد، پروفایل‌های منابع، بنچمارک | 🔨 در حال انجام |
| ۶ | ماژول نمایندگی (اسپانسری) | ⏳ برنامه‌ریزی شده |
| ۷ | بازطراحی کامل داشبورد | ⏳ برنامه‌ریزی شده |
| ۸ | امنیت و QA | ⏳ برنامه‌ریزی شده |
| ۹ | انتشار بالغ عمومی | ⏳ برنامه‌ریزی شده |

## 📄 مجوز و ارجاع

DR-VPN تحت مجوز **[GNU AGPL-3.0](LICENSE)** است که از PasarGuard به ارث رسیده.
پروژه‌های upstream تمام اعتبار کد پایه را دارند:

- [PasarGuard](https://github.com/PasarGuard/panel) — AGPL-3.0، © PasarGuard organization
- [Marzban](https://github.com/Gozargah/Marzban) — پروژه اصلی Marzban

اگر نسخه تغییریافته این نرم‌افزار را به‌عنوان سرویس شبکه اجرا می‌کنید، بند §13
AGPL-3.0 ایجاب می‌کند سورس متناظر را به کاربران سرویس خود ارائه دهید.
جزئیات در [NOTICE.md](NOTICE.md).

---

<p align="center">
  DR-VPN · یک هویت مستقل برای یک کدبیس آزموده
</p>
