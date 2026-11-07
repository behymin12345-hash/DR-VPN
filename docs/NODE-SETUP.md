# DR-VPN — Node Setup Guide / راهنمای نصب نود

> **English** · [فارسی](#فارسی)

The DR-VPN **panel** and the **node** are two separate components:

- The **panel** (this installer's default `drvpn install`) manages users,
  subscriptions and traffic. It does **not** run Xray itself.
- A **node** runs the actual Xray cores. Nodes connect to the panel over
  gRPC/REST with a shared API key. You need **at least one node** for users
  to get connections — it can be on the same server as the panel or on
  another server.

DR-VPN's node runtime is the upstream [PasarGuard node](https://github.com/PasarGuard/node)
(Go binary, Docker-based). DR-VPN wraps it so the panel ↔ node protocol stays
100% compatible.

## Quick start — single server (panel + node on the same box)

```bash
# 1. panel (if not installed yet)
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/behymin12345-hash/DR-VPN/main/scripts/drvpn.sh)" @ install

# 2. node on the SAME server
sudo drvpn install-node
```

The node installer asks (PasarGuard-style):

| Prompt | Meaning | Default |
|---|---|---|
| API Key | UUID shared with the panel — leave blank to auto-generate | random UUID |
| GRPC or REST | connection protocol to the panel | GRPC |
| SERVICE_PORT | the node port you will put in the panel | 62050 |
| Certificate | self-signed generated automatically (or paste your own) | generated |

## Connect the node to the panel

Open the dashboard → **Nodes → Create Node** and fill in:

| Field | Value |
|---|---|
| Node Name | anything (e.g. `main`) |
| Node Address | the node server's IP or domain (`127.0.0.1` if same box — use the public IP/domain for real users) |
| Node Port | the **SERVICE_PORT** you chose (default `62050`) |
| API Key | the **same UUID** as the node's `API_KEY` |
| API Port | `62051` |
| Certificate | paste the content of the node's certificate file (below) |
| Connection Type | GRPC (unless you picked REST) |

Show the node certificate to paste into the panel:

```bash
cat /var/lib/pg-node/certs/ssl_cert.pem
```

Change node settings later (port, API key, protocol):

```bash
sudo drvpn edit-env-dr      # opens the node .env (SERVICE_PORT / API_KEY / SERVICE_PROTOCOL)
sudo drvpn node-restart     # applies changes
```

Open these ports in your firewall/cloud security group: **62050**, **62051**
(and your proxy inbound ports, e.g. 443).

## Useful node commands

| Command | What it does |
|---|---|
| `drvpn install-node` | install the node runtime on this server |
| `drvpn edit-env-dr` | edit the node `.env` (port, API key, protocol) |
| `drvpn node-status` / `node-logs` / `node-restart` | manage the node service |
| `drvpn uninstall-node` | remove the node |
| `pg-node core-update` | update the node's Xray core |

## Multiple nodes

Repeat on each extra server: `sudo drvpn install-node` → create a new node
in the panel with that server's address and its own API key/certificate.
Each node can serve different groups/users from the panel.

---

## فارسی

**پنل** و **نود** دو جزء جدا هستند:

- **پنل** (نصب پیش‌فرض `drvpn install`) کاربران، اشتراک‌ها و ترافیک را مدیریت می‌کند و خودش Xray اجرا **نمی‌کند**.
- **نود** هسته‌های واقعی Xray را اجرا می‌کند و با یک API Key مشترک از طریق gRPC/REST به پنل وصل می‌شود. برای اینکه کاربران بتوانند وصل شوند **حداقل یک نود لازم است** — می‌تواند روی همان سرور پنل باشد یا روی سرور دیگر.

رانتایم نود DR-VPN همان [نود رسمی PasarGuard](https://github.com/PasarGuard/node) است (باینری Go مبتنی بر Docker) تا سازگاری کامل پنل ↔ نود حفظ شود.

## شروع سریع — یک سرور (پنل و نود روی هم)

```bash
# ۱. پنل (اگر هنوز نصب نیست)
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/behymin12345-hash/DR-VPN/main/scripts/drvpn.sh)" @ install

# ۲. نود روی همان سرور
sudo drvpn install-node
```

نصب‌کننده نود می‌پرسد (به سبک پاسارگارد):

| سوال | معنی | پیش‌فرض |
|---|---|---|
| API Key | UUID مشترک با پنل — خالی بگذار خودش بسازد | UUID تصادفی |
| GRPC یا REST | پروتکل اتصال به پنل | GRPC |
| SERVICE_PORT | پورت نود که در پنل وارد می‌کنی | 62050 |
| Certificate | خودکار self-signed می‌سازد (یا گواهی خودت را بده) | ساخته می‌شود |

## وصل‌کردن نود به پنل

داشبورد → **Nodes → Create Node** و پر کردن:

| فیلد | مقدار |
|---|---|
| Node Name | هر چیزی (مثلاً `main`) |
| Node Address | IP یا دامنه سرور نود (روی همین سرور: `127.0.0.1` — برای کاربر واقعی IP عمومی/دامنه) |
| Node Port | همان **SERVICE_PORT** (پیش‌فرض `62050`) |
| API Key | همان **UUID** که در `.env` نود است |
| API Port | `62051` |
| Certificate | محتوای فایل سرتیفیکیت نود (دستور زیر) |
| Connection Type | GRPC مگر REST انتخاب کرده باشی |

نمایش سرتیفیکیت نود برای پیست در پنل:

```bash
cat /var/lib/pg-node/certs/ssl_cert.pem
```

تغییر تنظیمات نود در آینده:

```bash
sudo drvpn edit-env-dr      # باز کردن .env نود (SERVICE_PORT / API_KEY / SERVICE_PROTOCOL)
sudo drvpn node-restart     # اعمال تغییرات
```

این پورت‌ها را در فایروال/Security Group باز کن: **62050**، **62051** (و پورت‌های اینباندهای پروکسی مثل 443).

## فرمان‌های مفید نود

| فرمان | کار |
|---|---|
| `drvpn install-node` | نصب رانتایم نود روی همین سرور |
| `drvpn edit-env-dr` | ویرایش `.env` نود (پورت، API Key، پروتکل) |
| `drvpn node-status` / `node-logs` / `node-restart` | مدیریت سرویس نود |
| `drvpn uninstall-node` | حذف نود |
| `pg-node core-update` | به‌روزرسانی هسته Xray نود |

## چند نود

برای هر سرور اضافه: `sudo drvpn install-node` → در پنل یک نود جدید با آدرس و API Key و سرتیفیکیت همان سرور بساز. هر نود می‌تواند از پنل، گروه/کاربران متفاوتی را سرو کند.
