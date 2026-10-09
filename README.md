# سیستم مدیریت، لاگر و پشتیبان‌گیری شرکت (Company Core Infrastructure)

این مخزن شامل مجموعه‌ای از سرویس‌ها، اسکریپت‌های پشتیبان‌گیری، ابزارهای ثبت و مانیتورینگ لاگ (Logger) و قوانین حسابرسی (Audit Rules) برای زیرساخت داخلی شرکت است.

---

## 📁 ساختار مخزن (Directory Structure)

```text
.
├── audit-rules/              # قوانین و پیکربندی‌های Auditd سیستم
│   └── company.rules
├── company/
│   ├── backup/               # اسکریپت‌ها و ساختار پشتیبان‌گیری
│   │   ├── backup.sh         # اسکریپت اصلی اجرای بکاپ
│   │   ├── backup.exclude    # لیست فایل‌ها/پوشه‌های استثنا در بکاپ
│   │   ├── daily/            # بکاپ‌های روزانه (tar.gz)
│   │   ├── weekly/           # بکاپ‌های هفتگی
│   │   ├── monthly/          # بکاپ‌های ماهانه
│   │   └── README.MD
│   ├── logger/               # سرویس و ماژول لاگر اختصاصی
│   │   ├── logger.py         # اسکریپت اصلی مانیتورینگ و ثبت لاگ
│   │   ├── audit.checkpoint  # وضعیت چک‌پوینت حسابرسی
│   │   ├── journal.cursor    # نشانگر آخرین وضعیت لاگ‌های systemd
│   │   └── README.MD
│   ├── Logs/                 # محل ذخیره‌سازی لاگ‌های متمرکز
│   │   ├── access.log
│   │   ├── auth.log
│   │   ├── backup.log
│   │   ├── error.log
│   │   ├── monitoring.log
│   │   ├── security.log
│   │   └── system.log
│   ├── Developers/           # دایرکتوری مربوط به تیم توسعه
│   ├── Finance/              # دایرکتوری بخش مالی
│   ├── HR/                   # دایرکتوری بخش منابع انسانی
│   └── Public/               # دایرکتوری اشتراک‌گذاری عمومی
├── systemd/                  # سرویس‌ها و تایمرهای Systemd
│   ├── company-backup.service
│   ├── company-backup.timer
│   ├── company-logger.service
│   ├── company-logger.timer
│   ├── company-logger-docker.service
│   └── company-logger-docker.timer
├── Dockerfile                # ایمیج Company Logger
├── compose.yaml              # سرویس Docker Compose
├── .dockerignore             # فایل‌های مستثنا از build context
├── DOCKER.md                 # راهنمای کامل Docker
└── screenshots/              # تصاویر و مستندات بصری سیستم
```

---

## 🚀 پیش‌نیازها و راه‌اندازی (Prerequisites & Setup)

### ۱. نصب پایتون و پیش‌نیازها
اسکریپت اصلی لاگر سیستم (`company/logger/logger.py`) نیاز به محیط پایتون ۳ دارد. برای نصب و آماده‌سازی:

```bash
# به‌روزرسانی مخازن لینوکس و نصب پایتون
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# (اختیاری) ایجاد و فعال‌سازی محیط مجازی پایتون
python3 -m venv venv
source venv/bin/activate

# نصب کتابخانه‌ها و نیازمندی‌ها (در صورت وجود requirements.txt)
# pip install -r requirements.txt
```

---

### ۲. پیکربندی سیستم حسابرسی (Auditd Rules)
برای نظارت بر تغییرات فایل‌ها و دسترسی‌های حساس مخزن، قوانین `audit-rules/company.rules` باید روی سرویس `auditd` سیستم اعمال شوند:

```bash
# ۱. نصب ابزار auditd
sudo apt install -y auditd audispd-plugins

# ۲. کپی کردن قوانین پروژه به سرویس سیستم
sudo cp audit-rules/company.rules /etc/audit/rules.d/company.rules

# ۳. اعمال و بارگذاری مجدد قوانین
sudo augenrules --load

# ۴. بررسی قوانین فعال شده
sudo auditctl -l
```

برای جستجو و بررسی لاگ‌های حسابرسی ثبت‌شده توسط auditd:
```bash
sudo ausearch -k company_audit
```

---

## ⚙️ پیکربندی و فعال‌سازی سرویس‌های Systemd

برای اجرای خودکار سرویس‌های پشتیبان‌گیری و مانیتورینگ در پس‌زمینه (Background Daemon):

```bash
# کپی کردن فایل‌های سرویس به مسیر systemd
sudo cp systemd/* /etc/systemd/system/

# بارگذاری مجدد پیکربندی systemd
sudo systemctl daemon-reload

# فعال‌سازی و شروع تایمرها
sudo systemctl enable --now company-backup.timer
sudo systemctl enable --now company-logger.timer
```

### بررسی وضعیت سرویس‌ها
```bash
# بررسی وضعیت تایمرها
sudo systemctl list-timers | grep company

# بررسی لاگ سرویس لاگر
sudo systemctl status company-logger.service
```

---

## 🐳 اجرای Company Logger با Docker

پروژه امکان اجرای لاگر در یک کانتینر را نیز دارد. در این معماری، **SSH، journald و auditd روی میزبان باقی می‌مانند**؛ کانتینر فقط لاگ‌های میزبان را می‌خواند، رویدادها را پردازش می‌کند و خروجی‌ها و checkpointها را در پوشه پروژه نگه می‌دارد.

### پیش‌نیازها

- Docker Engine و افزونه Docker Compose
- فعال بودن لاگ‌های SSH در journald و پیکربندی auditd روی میزبان
- وجود مسیرهای میزبان `/var/log/journal`، `/run/log/journal`، `/etc/machine-id` و `/var/log/audit/audit.log`
- اجرا از ریشه مخزن

### ساخت و اجرای دستی

```bash
mkdir -p company/Logs
docker compose config
docker compose build
docker compose run --rm company-logger
```

مشاهده خروجی‌ها:

```bash
ls -l company/Logs
tail -n 50 company/Logs/auth.log
tail -n 50 company/Logs/error.log
```

### زمان‌بندی با systemd میزبان (اختیاری)

فایل سرویس Docker پیش‌فرض فرض می‌کند مخزن در مسیر
`/home/admin/Workspace/linux-server-automation` قرار دارد. اگر مسیر شما متفاوت است، ابتدا `WorkingDirectory` و `ConditionPathExists` را در
`systemd/company-logger-docker.service` اصلاح کنید.

```bash
sudo cp systemd/company-logger-docker.service /etc/systemd/system/
sudo cp systemd/company-logger-docker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now company-logger-docker.timer
systemctl list-timers company-logger-docker.timer
```

**هشدار:** تایمر Docker را هم‌زمان با `company-logger.timer` قدیمی فعال نکن؛ اجرای هم‌زمان دو collector می‌تواند باعث تداخل در فایل‌های checkpoint و cursor شود. قبل از فعال‌کردن زمان‌بندی، یک اجرای دستی را بررسی کن.

راهنمای کامل تنظیمات، محدودیت‌های مانیتورینگ و دسترسی‌های لاگ در [DOCKER.md](DOCKER.md) آمده است.

---

## 🛠 اجزای اصلی سیستم

### ۱. سیستم پشتیبان‌گیری (Backup)
* **اسکریپت اصلی:** `company/backup/backup.sh`
* **استثناها:** فایل‌های تعریف‌شده در `backup.exclude` در نسخه بکاپ قرار نمی‌گیرند.
* **ساختار ذخیره‌سازی:** دسته‌بندی بکاپ‌ها براساس دوره‌های **روزانه** (`daily/`)، **هفتگی** (`weekly/`) و **ماهانه** (`monthly/`).

برای اجرای دستی بکاپ:
```bash
chmod +x company/backup/backup.sh
./company/backup/backup.sh
```

### ۲. لاگر و مانیتورینگ (Company Logger)
* **ماژول اصلی:** `company/logger/logger.py`
* **محل ذخیره‌سازی لاگ‌ها:** تمامی لاگ‌های تفکیک‌شده (دسترسی، خطاها، سیستم، پشتیبان‌گیری و امنیت) در مسیر `company/Logs/` ذخیره می‌شوند.

---

## 🔒 امنیت و دسترسی‌ها
* **سطوح دسترسی:** دایرکتوری‌های حساس نظیر `HR/`، `Finance/` و `Logs/` باید دارای سطح دسترسی محدود (Linux Permissions) باشند.
* **لاگ‌های امنیتی:** کلیه رویدادهای مربوط به احراز هویت و دسترسی در فایل‌های `auth.log` و `security.log` ثبت می‌شوند.