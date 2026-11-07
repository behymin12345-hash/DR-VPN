# DR-VPN | گزارش تحلیل معماری مخزن — STAGE 1

> مبنای تحلیل: مخزن `PasarGuard/panel` نسخه **v5.6.0** (commit `2b75db15`)، شاخه `upstream/main`
> تاریخ تحلیل: 2026-11-07 | وضعیت سورس: **دست‌نخورده** (طبق قانون Stage 1 هیچ تغییری اعمال نشده است)

---

## ۱. خلاصه اجرایی

PasarGuard یک پنل مدیریت پروکسی نسبتاً مدرن و از نظر معماری سالم است: بک‌اند تک‌پردازه‌ای FastAPI + SQLAlchemy async با پیش‌فرض SQLite+WAL، فرانت‌اند React 19 + Vite، سیستم Node خارجی مبتنی بر gRPC، و سرویس‌های اختیاری (NATS، تلگرام، وب‌هوک) که به‌صورت پیش‌فرض خاموش هستند. این معماری پایه خوبی برای DR-VPN است و بازنویسی کامل لازم ندارد.

**سه یافته مهم:**

1. ⛔ **کد منتشرشده upstream در حالت خام اجرا نمی‌شود**: در ۲۲ فایل Python، مجموعاً ۳۳ بند `except` به سبک Python 2 (`except X, Y:` به‌جای `except (X, Y):`) وجود دارد که `SyntaxError` قطعی هستند. این موضوع در مخزن رسمی `main` upstream نیز وجود دارد (راستی‌آزمایی شد). پیش از هر تست یا اجرایی، اصلاح مکانیکی این موارد الزامی است.
2. ⚠️ **هیچ قابلیت اسپانسری/نمایندگی وجود ندارد** — ماژول Reseller برای DR-VPN کاملاً جدید است. اما زیرساخت آن (مالکیت `User.admin_id` + سیستم RBAC سه‌سطحیه NONE/OWN/ALL + فیلد سهمیه در مدل `Admin`) از قبل آماده است و پیاده‌سازی را به‌مراتب ساده‌تر می‌کند.
3. ✅ **بهینه‌سازی منابع عمدتاً یعنی «تنظیم» نه «بازنویسی»**: تعداد پردازه‌ها از قبل حداقلی است؛ گلوگاه‌های اصلی، سیکل‌های سنگین scheduler و import های همیشگی ماژول‌های اختیاری هستند که با پروفایل‌های منابع قابل کنترل‌اند.

---

## ۲. مشخصات کدبیس

| شاخص | مقدار |
|---|---|
| زبان بک‌اند | Python ≥ 3.14 (FastAPI + uvicorn + uvloop روی Linux) |
| فریم‌ورک دیتابیس | SQLAlchemy 2 async + Alembic (۱۶۴ فایل migration) |
| دیتابیس‌های پشتیبانی‌شده | SQLite (پیش‌فرض، aiosqlite) / PostgreSQL (asyncpg) / MySQL (asyncmy) |
| فرانت‌اند | React 19.2 + Vite 8 + TypeScript + Tailwind 4 + shadcn/ui + TanStack Query + recharts |
| API Client | تولید خودکار با orval از OpenAPI (فایل تولیدشده ~۲۱٬۷۰۰ خط) |
| حجم بک‌اند | ~۶۱٬۰۰۰ خط Python در ۳۹۹ فایل (`app/`) |
| حجم فرانت‌اند | ~۱۲۲٬۰۰۰ خط TS/TSX (`dashboard/src/`) |
| تست‌ها | ۱۱۶ فایل تست pytest (API کامل، اشتراک، Node، NATS، نوتیفیکیشن، امنیت) |
| CLI | Typer + rich — فقط `generate-temp-key` و `version` |
| مجوز | **AGPL-3.0** — Copyright خط اول متعلق به «PasarGuard organization» |

### آمار LOC پوشه‌های بک‌اند

| پوشه | خطوط | نقش |
|---|---|---|
| `app/db/` | 20,244 | مدل‌ها، CRUD، migration ها (بزرگ‌ترین فایل: `crud/user.py` با ۲٬۳۶۷ خط) |
| `app/operation/` | 7,895 | لایه سرویس/بیزینس |
| `app/models/` | 4,935 | اسکیماهای Pydantic |
| `app/routers/` | 4,737 | لایه HTTP |
| `app/notification/` + `app/telegram/` | 7,065 | نوتیفیکیشن و ربات تلگرام |
| `app/jobs/` | 3,301 | کارهای زمان‌بندی‌شده |
| `app/node/` + `app/nats/` | 4,285 | ارتباط با Node ها |
| `app/subscription/` | 3,727 | تولید کانفیگ اشتراک (۹ فرمت) |
| `app/core/` | 2,234 | XRayConfig، HostManager، CoreManager |

---

## ۳. معماری بک‌اند — سه لایه

جریان درخواست: `routers/` (HTTP، مدل‌ها، dependency های احراز هویت) → `operation/` (بیزینس + اعتبارسنجی + اثر جانبی) → `db/crud/` (صرفاً statement های SQLAlchemy). همین `operation` توسط CLI، تلگرام و Job ها هم استفاده می‌شود؛ بنابراین هر قابلیت جدید (مثل Reseller) باید در همین سه لایه اضافه شود نه در router.

- **App assembly** (`app/app_factory.py`): `create_app()` بسته به `Role` (پیش‌فرض `ALL_IN_ONE`) دASHBOARD، تلگرام و `api_router` را mount می‌کند. exception handler های سراسری: 422/503/403/400.
- **Lifespan** (`app/lifecycle.py`): رجیستری سبک `on_startup/on_shutdown` — تمام سرویس‌ها (داشبورد، ربات، NATS، scheduler) از این آویزانند.
- **ورودی اصلی** (`main.py`): `uvicorn.run("main:create_app", workers=UVICORN_WORKERS)`؛ پیش‌فرض `workers=1`. با `workers>1` یا role تفکیک‌شده، NATS **الزامی** می‌شود (`require_nats_if_multiworker`). بدون SSL، اتصال روی IP عمومی مسدود و به localhost محدود می‌شود (امنیت پیش‌فرض خوب).

### رسترها (۱۸ روتر)

`/api/admin`، `/api/admin-role`، `/api/api_key`، `/api/user` (+HWID)، `/api/user_template`، `/api/group`، `/api/host`، `/api/core`، `/api/node`، `/api` (system + telegram hook)، `/api/settings`، `/api/client_template`، `/api/setup` (bootstrap با TempKey یک‌بارمصرف)، `/api/admin/passkey` (WebAuthn)، `/sub/{token}` (عمومی و بدون احراز هویت)، `/health`.

---

## ۴. مدل داده (جداول کلیدی)

در `app/db/models.py` (۱٬۱۰۴ خط، همه مدل‌ها در یک فایل):

| مدل | نکات کلیدی برای DR-VPN |
|---|---|
| `Admin` | `username`، `hashed_password` (bcrypt)، سهمیه: `used_traffic`/`data_limit`/`status` (active/disabled/limited)، برندینگ اشتراک هر ادمین (`sub_domain`، `profile_title`، `support_url`)، `role_id` + `permission_overrides` JSON |
| `AdminRole` | **RBAC سه‌سطحیه**: `PermissionScope.NONE=0 / OWN=1 / ALL=2` روی ۱۳ منبع (users, admins, nodes, …) + `RoleLimits` (سهمیه کاربر/ترافیک/انقضا/HWID) + سه نقش seed (owner/administrator/operator) |
| `User` | `admin_id` (FK nullable به `admins.id`) = **مالک کاربر**، `status` (active/disabled/limited/expired/on_hold)، `used_traffic`/`data_limit`/`data_limit_reset_strategy`، `expire`، `online_at`، `hwid_limit`، M2M با `Group` |
| `Node` | status/connecting/error/limited، `core_config_id`، سهمیه ترافیک node، `connection_type` grpc/rest |
| `CoreConfig` | `CoreType`: xray / wg / mtproto / singbox |
| سایر | `ProxyInbound`، `ProxyHost` (سطح وسیعی از override ها)، `Group`، `UserTemplate`، `APIKey` (hashed، محدودیت تعداد درخواست)، `TempKey`، `Settings` (یک ردیف JSON: تلگرام/وب‌هوک/اشتراک/HWID/cleanup)، `JWT` (یک ردیف secret تصادفی)، `NodeUserUsage` (باکت‌های ۱۰ دقیقه‌ای) |

**نتیجه برای ماژول Reseller:** الگوی «ادمین + سهمیه + مالکیت کاربر» دقیقاً همان چیزی است که سیستم نمایندگی نیاز دارد. Sponsor-Admin = یک `Admin` با `AdminRole` جدید (مثلاً `sponsor`) با scope OWN روی users، محدودیت‌های `RoleLimits`، و گزارش‌گیری سهمیه. فیلدهای احتمالاً جدید: تعداد مجاز کاربر/ترافیک در سطح «قرارداد نمایندگی» و شفاف‌سازی report — طراحی دقیق در Stage 5 پس از خواندن کامل `operation/permissions.py` و `crud/admin.py`.

---

## ۵. احراز هویت و RBAC

- **JWT بیرر HS256** بدون session سمت سرور؛ secret از جدول `jwt` (با aiocache). payload شامل `sub`، `access`، `iat`، `aid` و `binding` = HMAC روی `hashed_password` → تغییر رمز، تمام توکن‌های قبلی را بی‌اعتبار می‌کند (طراحی هوشمند).
- رمز عبور: bcrypt در `ThreadPoolExecutor` جدا (بدون بلاک شدن event loop).
- **API Key**: فرمت `pg_key_<uuid>`، ذخیره هش‌شده، شمارنده مصرف، انقضا، مجوزهای محدودشده — هرگز سطح owner.
- **Passkey/WebAuthn** اختیاری (`PASSKEY_RP_ID`).
- **اعمال مالکیت در سطح SQL**: `get_scope_admin_id()` شناسه ادمین را به CRUD می‌دهد و کوئری‌ها `User.admin_id == admin_id` اضافه می‌کنند (دو لایه: dependency روتر + `@check_permission` در operation). برای Reseller دقیقاً همین مکانیزم استفاده می‌شود.

---

## ۶. ارتباط با Node ها و XRay

- **XRay به‌صورت پروسه محلی اجرا نمی‌شود** — پنل فقط config تولید/اعتبارسنجی می‌کند؛ هسته‌ها روی Node های Go خارجی (باینری `pasarguard-node`) از طریق `pasarguard-node-bridge` (gRPC/grpclib یا REST) اجرا می‌شوند.
- **NATS صرفاً client است و embedded نیست**؛ پیش‌فرض `NATS_ENABLED=False` و در استقرار تک‌پردازه‌ای کاملاً غیرفعال و بدون هزینه.
- `app/node/nats_memory.py` (۹۷۰ خط): اگر NATS فعال و workers>1 باشد، صف همگام‌سازی کاربران از حافظه in-process به JetStream KV مشترک منتقل می‌شود — در حالت پیش‌فرض یک‌پردازه‌ای بی‌اثر و بارگذاری نمی‌شود.
- `XRayConfig` (`app/core/xray.py`): اعتبارسنجی tag ها، TLS SAN، WireGuard allocation، transport های متعدد (ws/grpc/kcp/splithttp/masque/…). `HostManager` با کش ۱۰ ثانیه‌ای snapshot و انتشار تغییرات بین worker ها.
- ۹ فرمت خروجی اشتراک: links، links_base64، xray، sing-box، clash، clash-meta، outline، wireguard، block + صفحه HTML اشتراک با Jinja + کش LRU (TTL 15s، حداکثر ۴٬۰۹۶ مدخل).

---

## ۷. پردازه‌ها و Jobs زمان‌بندی‌شده

### پردازه‌ها در استقرار کامل (Docker)

| پردازه | نقش | وضعیت |
|---|---|---|
| `main.py` (uvicorn) | API + داشبورد + همه jobs (پیش‌فرض all-in-one) | اصلی |
| `node_worker.py` / `scheduler_worker.py` | role های تفکیک‌شده | **deprecated** (حذف در v7) — فقط Docker/start.sh |
| `pasarguard-cli.py` | CLI کوتاه‌عمر | گاه‌به‌گاه |
| باینری Go node + XRay | هسته واقعی پروکسی | خارج از این مخزن |

### جدول Jobs (مهم‌ترین‌ها — همه داخل همان پردازه API با APScheduler)

| Job | اینتروال پیش‌فرض | هزینه |
|---|---|---|
| `record_user_usages` | **۱۰ ثانیه** | ⛔ سنگین‌ترین: RPC به همه node ها + bulk-write به `NodeUserUsage` + آپدیت `User.used_traffic` و `Admin.used_traffic` |
| `node_health_check` | ۱۰ ثانیه | متوسط: probe هر node (semaphore=5) |
| `limit_admins` | ۱۰ ثانیه | متوسط: `SELECT ... FOR UPDATE` |
| `record_node_usages` | ۳۰ ثانیه | متوسط |
| `expire_users` / `limit_users` / `on_hold_to_active` | ۳۰ ثانیه (staggered) | سنگین فقط هنگام transition |
| `send_notifications` + `process_notification_queues` | ۳۰ ثانیه | صفر وقتی کانال‌ها خاموش (early-return) |
| `reset_user_data_usage` | ۶۰۰ ثانیه | سبک |
| `remove_old_inbounds`، `cleanup_subscription_updates`، `cleanup_node_sync` | ۳۰۰–۶۰۰ ثانیه | سبک |
| `remove_expired_users`، `delete_expired_reminders` | ۱–۶ ساعت | سبک |
| `cleanup_retention_data` + rollup | ۱ ساعت | سنگین فقط اگر retention تنظیم شده باشد (پیش‌فرض: خاموش → هیچ) |
| `gather_nodes_stats` | ۲۵ ثانیه | **صفر** به‌صورت پیش‌فرض (فقط PostgreSQL + تنظیم اختیاری) |

**نکته کلیدی برای پروفایل Minimal:** همه اینتروال‌ها با متغیرهای `JOB_*_INTERVAL` قابل تنظیم‌اند (`config.py:197-212`) — یعنی پروفایل منابع بدون تغییر کد قابل پیاده‌سازی است؛ فقط مقادیر پیش‌فرض و مستندسازی باید اضافه شود.

---

## ۸. کش، لاگ و میانه‌ها

- **کش**: aiocache (SimpleMemoryCache) روی ۵ نقطه: تنظیمات DB (بدون TTL + invalidation دستی/بین-process با NATS)، JWT secret، inbounds، hosts (TTL 10s)، قالب‌های اشتراک. + LRU اشتراک (TTL 15s). بدون Redis در هیچ‌جای پروژه — برای VPS کوچک مناسب است.
- **لاگ**: فقط کنسول به‌صورت پیش‌فرض؛ فایل با `SAVE_LOGS_TO_FILE=True` و rotation (سایز یا زمان، ۷۲ نسخه پشتیبان) — **rotation موجود است ولی دوبل خاموش**. هزینه جاری: ~۲ خط INFO برای هر request (middleware زمان پردازش).
- **تنظیمات DB-محور**: تلگرام/وب‌هوک/نوتیفیکیشن پیش‌فرض خاموش؛ per-event toggles پیش‌فرض روشن ولی بدون مقصد بی‌اثر.

---

## ۹. فرانت‌اند (dashboard/)

- React 19 + Vite 8 + Tailwind 4 + shadcn/ui (۴۶ کامپوننت ui) + ۱۵ ماژول feature + TanStack Query + recharts + monaco (ادیتور کانفیگ) + PWA (workbox).
- مسیریابی: `createHashRouter` دستی (سازگار با Telegram MiniApp)؛ همه صفحات lazy.
- **i18n از قبل کامل**: i18next با ۴ زبان (en/fa/ru/zh؛ هرکدام ~۴٬۲۰۰ خط)، RTL خودکار با `document.dir`، تقویم شمسی با `date-fns-jalali` + `react-day-picker/persian`، fallback انگلیسی. یعنی «فارسی + RTL» DR-VPN روی زیرساخت موجود سوار می‌شود؛ فقط پیش‌فرض باید fa شود و ترجمه‌های DR-VPN اضافه شوند.
- **برندینگ — سطوح اصلی**: `<title>` در `index.html`، لوگو در login و sidebar (۴ مورد)، کلیدهای ترجمه `pasarguard` در ۴ locale، footer «PasarGuard Team»، `constants/Project.ts` (URL های repo/donation/docs)، `use-version-check` (GitHub API)، نام پکیج‌های `@pasarguard/*`، workbox cache name. مجموعاً ۱۲۹ خط در ۶۸ فایل + فایل‌های favicon/logos در `public/statics/`.
- خروجی build استاتیک است و FastAPI آن را در `/dashboard/` serve می‌کند (با کش immutable برای asset ها).

---

## ۱۰. استقرار، CI و تست‌ها

- **Docker**: image با uv + python:3.14-slim؛ `start.sh` اول `alembic upgrade head` بعد `python main.py`.
- **systemd**: `install_service.sh` یونیت ساده `pasarguard.service` (اجرای `main.py` با `.venv`) — پایه خوبی برای نصب‌کننده DR-VPN.
- **CI فعلی**: CodeQL (API/فرانت)، ruff-check، test-database-migrations، build Docker — ۷ workflow.
- **تست‌ها**: `TestClient` واقعی FastAPI روی SQLite/aiosqlite با `StaticPool` + اجرای migration alembic + جداسازی per-xdist-worker. پوشش: CRUD کامل API، permission-leak، اشتراک (کش، UA، فرمت‌ها)، node sync/health، NATS، نوتیفیکیشن، retention، TLS، امنیت. اجرا با `make test` (pytest-xdist).

---

## ۱۱. گلوگاه‌های منابع و فرصت‌های بهینه‌سازی (تحلیل Stage 1)

### مصرف حافظه پایه — عوامل ثابت

1. **Python baseline**: FastAPI + SQLAlchemy + pydantic v2 + اپ؛ با `workers=1` تک‌پردازه است. `aiogram`، `webauthn`، `nats-py` و `monaco`-معادل‌های بک‌اند **همیشه import می‌شوند** حتی وقتی قابلیت خاموش است (import سراسری `app/telegram` و `app/notification` در `runs_panel`) → فرصت lazy-import.
2. **uvloop** روی Linux فعال (auto) — مفید.
3. **داشبورد**: build استاتیک؛ حافظه سرور را نمی‌گیرد (فقط دیسک).

### فرصت‌های مشخص بهینه‌سازی (برای Stage 3)

| # | فرصت | اثر تخمینی | ریسک |
|---|---|---|---|
| O1 | پروفایل منابع = پیش‌تنظیم `JOB_*_INTERVAL` (مثلاً minimal: record_usages از 10s→60s، health 10s→60s، review 30s→120s) | کاهش چشمگیر CPU و wake-up های DB | کم — فقط تأخیر آمار |
| O2 | lazy-import برای `aiogram`، `webauthn`، `nats` وقتی غیرفعال | کاهش RAM پایه | متوسط — باید import chain ها دقیق بررسی شود |
| O3 | حذف خط لاگ دوم «request phases» و سطح قابل‌تنظیم access-log در minimal | کاهش I/O | کم |
| O4 | بررسی `deepcopy` کل snapshot hosts در هر درخواست اشتراک (کش 10s) | کاهش CPU در ترافیک بالا | متوسط |
| O5 | `GZIP_MINIMUM_SIZE` و سطح gzip قابل‌تنظیم؛ خاموش کردن gzip در minimal برای پاسخ‌های حجیم | CPU ↔ پهنای‌باند | کم |
| O6 | سقف LRU اشتراک (۴۰۹۶) و TTL برای پروفایل minimal قابل کاهش | کاهش RAM | کم |
| O7 | اضافه‌کردن `PRAGMA synchronous=NORMAL` (با WAL سازگار و امن) + `PRAGMA cache_size` محدود | تعادل پرف/Durability | کم |
| O8 | حذف/به تعویق انداختن dependency های بلااستفاده (بررسی: `Deprecated`، `commentjson`، `rich` فقط CLI، ...) | کاهش RAM پایه + زمان startup | متوسط — نیاز به تست import کامل |
| O9 | پیش‌فرض `ALLOWED_ORIGINS=*` → سفت‌کردن به same-origin پیش‌فرض | امنیت | کم |

### چیزهایی که «بهینه‌سازی نمی‌خواهند» (برای جلوگیری از کار بیهوده)

- تعداد پردازه‌ها از قبل حداقلی است (تک‌پردازه، بدون XRay محلی، بدون NATS پیش‌فرض).
- SQLite از قبل WAL + busy_timeout دارد.
- صف‌های نوتیفیکیشن در حالت خاموش عملاً هزینه صفر دارند (early-return).
- `gather_nodes_stats` پیش‌فرض صفر است.

> ⚠️ طبق قواعد پروژه: هیچ عدد RAM/CPU در این گزارش ادعا نشده است. اندازه‌گیری واقعی پس از اجرای پنل (بعد از رفع خطاهای syntax) و با اسکریپت‌های بنچمارک Stage 3 انجام می‌شود.

---

## ۱۲. یافته بحرانی: خطاهای Syntax در سورس upstream

- **۳۳ بند** `except X, Y:` (بدون پرانتز — سینتکس Python 2) در **۲۲ فایل**؛ همگی `SyntaxError` قطعی روی CPython 3.14.
- راستی‌آزمایی شد: همین کد در `main` مخزن رسمی upstream هم موجود است (مثال: `app/lifecycle.py:24`).
- فایل‌های کلیدی متأثر: `main.py`، `app/lifecycle.py`، `app/operation/permissions.py`، `app/utils/jwt.py`، `app/db/crud/admin.py`، `app/subscription/share.py`، `app/jobs/record_usages.py`، `app/core/hosts.py`، `app/core/xray.py`، `app/node/nats_memory.py`، `app/telegram/fsm_storage.py`، `app/notification/*` و …
- همه به‌صورت مکانیکی قابل رفع‌اند: `except X, Y:` → `except (X, Y):`
- **نتیجه**: اولین اقدام اجرایی (ابتدای Stage 3/4) باید رفع این ۳۳ مورد و سپس اجرای موفق `pytest` باشد تا baseline سالم به دست آید. تا آن لحظه هیچ تست یا بنچمارکی معتبر نیست.

فهرست کامل (فایل:خط): main.py:62؛ app/lifecycle.py:24؛ app/core/hosts.py:611,624؛ app/core/manager.py:83؛ app/core/xray.py:286؛ app/db/crud/admin.py:81؛ app/db/crud/general.py:216؛ app/jobs/record_usages.py:831؛ app/jobs/send_notifications.py:40؛ app/models/host.py:854؛ app/nats/router.py:97؛ app/node/nats_memory.py:182؛ app/notification/client.py:71؛ app/notification/nats_queue.py:335,353,363؛ app/operation/permissions.py:42؛ app/operation/subscription.py:158,170,181,310؛ app/subscription/share.py:203,216؛ app/telegram/fsm_storage.py:143,288,312,336؛ app/telegram/handlers/admin/bulk_actions.py:99؛ app/utils/crypto.py:93؛ app/utils/helpers.py:41؛ app/utils/jwt.py:62

---

## ۱۳. پیامدهای مجوز (AGPL-3.0)

- متن LICENSE دست‌نخورده می‌ماند (خط Copyright «PasarGuard organization» حفظ می‌شود)؛ attribution اضافه در `NOTICE.md`.
- DR-VPN به‌عنوان اثر مشتق، **باید** AGPL-3.0 منتشر شود و به کاربران شبکه سورس corresponding را ارائه دهد (بخش ۱۳) — در README و INSTALL درج خواهد شد.
- خط نسبیت با Marzban (Gozargah) و PasarGuard در README هر دو زبان ذکر می‌شود.
- نام‌ها/URL های upstream که به خدمات upstream اشاره دارند (donation، t.me، docs.pasarguard.org) در سطوح کاربری DR-VPN حذف یا جایگزین می‌شوند، اما اعلان‌های مجوزی حذف نمی‌شوند.

---

## ۱۴. برنامه توسعه به‌روزشده (بر پایه این تحلیل)

| مرحله | کارها | نکته به‌روز |
|---|---|---|
| ۲ | برندینگ: لوگو + `assets/branding/` + جایگزینی ۱۲۹ رفرنس برند + توکن‌های رنگ | i18n و RTL از قبل هست — فقط پیش‌فرض fa + ترجمه‌های DR-VPN |
| ۳ | بهینه‌سازی: رفع ۳۳ SyntaxError → baseline pytest سبز → پروفایل‌های منابع (O1, O2, O7, O8) → اسکریپت‌های بنچمارک | اجرای pytest روی ویندوز با uv |
| ۴ | هسته عملکردی: اجرای کامل تست‌ها + راستی‌آزمایی دستی API + برندینگ CLI | تمرکز روی تست‌های موجود |
| ۵ | ماژول Reseller: `AdminRole` جدید + `RoleLimits` گسترش‌یافته + router/operation/crud + تست + بخش داشبورد | از زیرساخت RBAC و `admin_id` استفاده می‌شود |
| ۶ | فرانت‌اند: سیستم طراحی DR-VPN + صفحه لاگین/سایدبار/فوتر + سوییچر زبان با پیش‌فرض فارسی | retheme روی کد موجود |
| ۷ | نصب‌کننده: ۶ اسکریپت + یونیت systemd + uv-managed Python 3.14 | تست لینوکسی deferred (به‌صورت صادقانه مستند می‌شود) |
| ۸ | تست و امنیت: اجرای کامل + بازبینی مسیرهای بی‌احراز + rate-limit + secrets در لاگ | شامل O9 |
| ۹ | انتشار: README (fa/en) + NOTICE + CHANGELOG + INSTALL + API docs + Actions | بررسی نهایی AGPL |

---

## ۱۵. موارد نامشخص / ریسک‌ها

1. **دلیل خطاهای syntax در upstream نامشخص است** (شاید خطای انسانی، شاید عمدی). برای ما فقط پیامد عملی مهم است: قبل از هر اجرایی باید رفع شوند.
2. **باینری Node (Go)** خارج از این مخزن است؛ DR-VPN آن را «همچون قبل» با attribution نگه می‌دارد. اگر بعداً برندینگ آن خواسته شود، نیاز به build جداگانه از مخزن `PasarGuard/node` دارد (خارج از محدوده فعلی).
3. **بنچمارک واقعی روی ویندوز معتبر نیست** (اهداف 256/512MB مربوط به Linux است) — تا آماده شدن WSL/VPS، فقط اسکریپت‌ها آماده می‌شوند.
4. **نسخه client تولیدشده orval (5.5.1) عقب‌تر از backend (5.6.0) است** — در Stage 6 بازتولید می‌شود.
5. Python ≥3.14 برای نصب‌کننده یعنی نصب Python از طریق uv (پایتون توزیع‌های Ubuntu قدیمی‌تر است) — در طراحی installer لحاظ شد.
