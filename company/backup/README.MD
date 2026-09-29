# Backup Script Documentation

## Overview

این اسکریپت Bash برای تهیه و مدیریت Backup از دایرکتوری اصلی پروژه استفاده می‌شود.

اسکریپت در هر اجرا:

1. وجود مسیر Source را بررسی می‌کند.
2. فضای آزاد دیسک را بررسی می‌کند.
3. یک Backup روزانه با فرمت `tar.gz` ایجاد می‌کند.
4. در روز یکشنبه، Backup روزانه را به عنوان Backup هفتگی ثبت می‌کند.
5. در روز اول هر ماه، Backup روزانه را به عنوان Backup ماهانه ثبت می‌کند.
6. Backupهای قدیمی را بر اساس سیاست Retention حذف می‌کند.
7. تمام رویدادهای مهم را در فایل Log ثبت می‌کند.

---

## Script Configuration

### Source Directory

```bash
SOURCE="/home/admin/Workspace/company"
```

مسیر اصلی داده‌هایی که باید Backup شوند.

### Backup Directories

```text
/home/admin/Workspace/company/Backup/
├── daily/
├── weekly/
└── monthly/
```

مقادیر مربوط به این مسیرها در اسکریپت به شکل زیر تعریف شده‌اند:

```bash
BACKUP_DIR="$SOURCE/Backup"
DAILY_DIR="$BACKUP_DIR/daily"
WEEKLY_DIR="$BACKUP_DIR/weekly"
MONTHLY_DIR="$BACKUP_DIR/monthly"
```

### Log File

```bash
LOG_FILE="$SOURCE/Logs/backup.log"
```

تمام پیام‌های مربوط به اجرای Backup در این فایل ثبت می‌شوند.

### Retention Policy

```bash
DAILY_KEEP=7
WEEKLY_KEEP=4
MONTHLY_KEEP=12
```

سیاست نگهداری Backupها:

| نوع Backup | تعداد نگهداری |
|---|---:|
| Daily | 7 |
| Weekly | 4 |
| Monthly | 12 |

Backupهای قدیمی‌تر از این تعداد در مرحله Cleanup حذف می‌شوند.

### Minimum Free Disk Space

```bash
MIN_FREE_GB=1
```

حداقل فضای آزاد موردنیاز `1 GB` است. اگر فضای آزاد کمتر از این مقدار باشد، اسکریپت قبل از ایجاد Backup متوقف می‌شود.

---

## Backup Exclusions

اسکریپت از فایل زیر برای تعیین مواردی که نباید در Backup قرار بگیرند استفاده می‌کند:

```bash
EXCLUDE_FILE="$SOURCE/backup/backup.exclude"
```

این فایل با گزینه `--exclude-from` به دستور `tar` داده می‌شود.

بنابراین محتویات `backup.exclude` باید مطابق فرمت مورد انتظار `tar` باشند.

---

## Logging

تابع `log` پیام‌ها را همراه با Timestamp در فایل Log ذخیره می‌کند:

```bash
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}
```

نمونه قالب Log:

```text
[2026-09-29 00:00:00] ========== Backup started ==========
```

خطاهای مربوط به اجرای `tar` نیز مستقیماً به همین فایل Log اضافه می‌شوند.

---

## Directory Preparation

در ابتدای اجرای Backup، دایرکتوری‌های موردنیاز ایجاد می‌شوند:

```bash
mkdir -p "$DAILY_DIR"
mkdir -p "$WEEKLY_DIR"
mkdir -p "$MONTHLY_DIR"

touch "$LOG_FILE"
```

استفاده از `mkdir -p` باعث می‌شود در صورت وجود نداشتن مسیرها، آن‌ها ساخته شوند.

---

## Execution Flow

جریان کلی اجرای اسکریپت به شکل زیر است:

```text
Start
  │
  ├── Prepare backup directories
  │
  ├── Initialize log
  │
  ├── Check source directory
  │       └── Missing → Exit 1
  │
  ├── Check free disk space
  │       └── Less than 1 GB → Exit 1
  │
  ├── Create daily backup
  │       └── Failed → Remove incomplete file + Exit 1
  │
  ├── Is today Sunday?
  │       └── Yes → Create weekly hard link
  │
  ├── Is today the first day of month?
  │       └── Yes → Create monthly hard link
  │
  ├── Cleanup old backups
  │
  └── Finish successfully
```

---

## Date Variables

اسکریپت برای تعیین نوع Backup از تاریخ سیستم استفاده می‌کند:

```bash
DATE=$(date '+%Y-%m-%d')
MONTH=$(date '+%Y-%m')
DAY=$(date '+%u')
DAY_OF_MONTH=$(date '+%d')
```

معنای متغیرها:

| Variable | Meaning | Example |
|---|---|---|
| `DATE` | تاریخ کامل | `2026-09-29` |
| `MONTH` | ماه جاری | `2026-09` |
| `DAY` | شماره روز هفته، مطابق ISO | `1` تا `7` |
| `DAY_OF_MONTH` | روز ماه | `01` تا `31` |

در این اسکریپت مقدار `7` برای یکشنبه در نظر گرفته شده است.

---

## Daily Backup

Backup روزانه در هر اجرای موفق اسکریپت ایجاد می‌شود.

نام فایل:

```text
backup-YYYY-MM-DD.tar.gz
```

برای مثال:

```text
backup-2026-09-29.tar.gz
```

مسیر:

```text
$SOURCE/Backup/daily/
```

### Command

منطق اصلی ایجاد Backup:

```bash
tar \
    --exclude-from="$EXCLUDE_FILE" \
    -czf "$DAILY_BACKUP" \
    -C "$(dirname "$SOURCE")" \
    "$(basename "$SOURCE")"
```

### Details

- `--exclude-from` فایل Exclusion را اعمال می‌کند.
- `-c` یک Archive جدید ایجاد می‌کند.
- `-z` خروجی را با gzip فشرده می‌کند.
- `-f` مسیر فایل خروجی را مشخص می‌کند.
- گزینه `-C` باعث می‌شود Archive نسبت به Parent Directory ساخته شود.

اگر Backup موفق باشد، اندازه فایل نیز در Log ثبت می‌شود.

اگر Backup شکست بخورد:

1. خطا در Log ثبت می‌شود.
2. فایل Backup ناقص حذف می‌شود.
3. اسکریپت با Exit Code `1` متوقف می‌شود.

---

## Weekly Backup

Backup هفتگی فقط در روز یکشنبه ایجاد می‌شود:

```bash
if [ "$DAY" -eq 7 ]; then
```

نام فایل:

```text
backup-week-YYYY-MM-DD.tar.gz
```

مثال:

```text
backup-week-2026-09-27.tar.gz
```

مسیر:

```text
$SOURCE/Backup/weekly/
```

### Hard Link

Backup هفتگی با دستور زیر ایجاد می‌شود:

```bash
ln "$DAILY_BACKUP" "$WEEKLY_BACKUP"
```

این عملیات یک **Hard Link** به همان فایل Backup روزانه ایجاد می‌کند و یک Archive جدید را دوباره تولید نمی‌کند.

در نتیجه، Backup روزانه و هفتگی به یک Inode و یک محتوای فیزیکی روی فایل‌سیستم اشاره می‌کنند تا زمانی که یکی از Linkها حذف شود.

---

## Monthly Backup

Backup ماهانه در اولین روز هر ماه ایجاد می‌شود:

```bash
if [ "$DAY_OF_MONTH" -eq "01" ]; then
```

نام فایل:

```text
backup-month-YYYY-MM.tar.gz
```

مثال:

```text
backup-month-2026-09.tar.gz
```

مسیر:

```text
$SOURCE/Backup/monthly/
```

مانند Backup هفتگی، Backup ماهانه نیز با Hard Link ایجاد می‌شود:

```bash
ln "$DAILY_BACKUP" "$MONTHLY_BACKUP"
```

بنابراین فایل ماهانه نیز یک Archive مستقل جدید نیست و به فایل Backup روزانه همان روز اشاره می‌کند.

---

## Cleanup

تابع `cleanup_old_backups` برای حذف Backupهای قدیمی استفاده می‌شود.

### Daily Cleanup

اسکریپت:

1. فایل‌های `backup-*.tar.gz` را پیدا می‌کند.
2. آن‌ها را بر اساس Modification Time مرتب می‌کند.
3. جدیدترین 7 فایل را نگه می‌دارد.
4. بقیه را حذف می‌کند.

```bash
tail -n +$((DAILY_KEEP + 1))
```

### Weekly Cleanup

برای فایل‌های زیر:

```text
backup-week-*.tar.gz
```

جدیدترین 4 فایل نگه داشته می‌شوند.

### Monthly Cleanup

برای فایل‌های زیر:

```text
backup-month-*.tar.gz
```

جدیدترین 12 فایل نگه داشته می‌شوند.

---

## Retention Behavior

Retention بر اساس **تعداد فایل‌ها** و **Modification Time** انجام می‌شود، نه بر اساس سن تقویمی Backup.

بنابراین:

- Daily: حداکثر 7 فایل
- Weekly: حداکثر 4 فایل
- Monthly: حداکثر 12 فایل

تعداد واقعی Backupهای قابل بازیابی از نظر محتوای مستقل می‌تواند کمتر از مجموع این اعداد باشد، چون Weekly و Monthly با Hard Link به Daily Backup متصل هستند.

---

## Disk Space Check

قبل از ایجاد Backup، فضای آزاد مسیر Backup با دستور `df` بررسی می‌شود:

```bash
FREE_GB=$(df -BG "$BACKUP_DIR" | awk 'NR==2 {gsub("G","",$4); print $4}')
```

اگر مقدار فضای آزاد کمتر از مقدار تنظیم‌شده در `MIN_FREE_GB` باشد:

```text
ERROR: Not enough disk space. Free: XGB
```

در Log ثبت شده و اسکریپت با Exit Code `1` متوقف می‌شود.

در صورت عبور از این بررسی، فضای آزاد نیز در Log ثبت می‌شود.

---

## Exit Codes

### Success

```bash
exit 0
```

یعنی اجرای Backup با موفقیت به پایان رسیده است.

### Failure

```bash
exit 1
```

در شرایطی مانند موارد زیر استفاده می‌شود:

- Source Directory وجود ندارد.
- فضای آزاد کافی نیست.
- Daily Backup ایجاد نشده است.
- ایجاد Weekly Hard Link با خطا مواجه شده است.
- ایجاد Monthly Hard Link با خطا مواجه شده است.

---

## File Naming Convention

ساختار نام‌گذاری فایل‌ها:

```text
daily/
└── backup-YYYY-MM-DD.tar.gz

weekly/
└── backup-week-YYYY-MM-DD.tar.gz

monthly/
└── backup-month-YYYY-MM.tar.gz
```

---

## Example Directory Structure

پس از چند اجرا، ساختار Backup می‌تواند شبیه این باشد:

```text
/home/admin/Workspace/company/
├── Backup/
│   ├── daily/
│   │   ├── backup-2026-09-25.tar.gz
│   │   ├── backup-2026-09-26.tar.gz
│   │   └── backup-2026-09-27.tar.gz
│   │
│   ├── weekly/
│   │   └── backup-week-2026-09-27.tar.gz
│   │
│   └── monthly/
│       └── backup-month-2026-09.tar.gz
│
├── Logs/
│   └── backup.log
│
└── backup/
    └── backup.exclude
```

---

## Operational Requirements

برای اجرای صحیح اسکریپت، موارد زیر باید برقرار باشند:

1. Bash روی سیستم موجود باشد.
2. کاربری که اسکریپت را اجرا می‌کند به Source Directory دسترسی داشته باشد.
3. کاربر دسترسی ایجاد و حذف فایل در مسیر Backup داشته باشد.
4. دستورات مورد استفاده مانند `tar`, `df`, `awk`, `find`, `sort`, `tail`, `cut`, `xargs`, `rm`, `ln` و `du` در محیط سیستم در دسترس باشند.
5. فایل Exclusion در مسیر تعریف‌شده در صورت نیاز به Exclusionهای Backup وجود داشته باشد.

---

## Important Implementation Notes

### 1. Backup Directory داخل Source قرار دارد

مسیر Backup به صورت زیر تعریف شده است:

```bash
BACKUP_DIR="$SOURCE/Backup"
```

یعنی Backupها داخل خود Source ذخیره می‌شوند.

این موضوع از نظر طراحی Backup مهم است، چون Archive در همان درخت دایرکتوری‌ای قرار دارد که قرار است Backup شود. رفتار نهایی آن نسبت به `tar` به تنظیمات `backup.exclude` وابسته است. برای جلوگیری از Backup شدن Archiveهای قبلی، بهتر است مسیر `Backup` در فایل Exclusion مشخص شده باشد.

### 2. Exclusion File نیز داخل Source است

فایل Exclusion در:

```text
$SOURCE/backup/backup.exclude
```

قرار دارد. بنابراین تنظیم درست این فایل برای جلوگیری از وارد شدن فایل‌ها و دایرکتوری‌های ناخواسته به Archive اهمیت دارد.

### 3. Weekly و Monthly واقعاً Archive جدید تولید نمی‌کنند

این دو نوع Backup با `ln` ایجاد می‌شوند و Hard Link هستند. در نتیجه محتوای آن‌ها همان محتوای Daily Backup مربوط به همان روز است.

### 4. پیام Log مربوط به Monthly

در بخش Monthly، پیام زیر ثبت می‌شود:

```text
Weekly backup uses hard link
```

این پیام با بخش Monthly مطابقت ندارد و به نظر می‌رسد متن Log به‌صورت اشتباهی از بخش Weekly کپی شده باشد. رفتار واقعی کد همچنان ایجاد Monthly Hard Link است.

---

## Summary

این اسکریپت یک سیستم Backup محلی با سه سطح نگهداری فراهم می‌کند:

```text
Daily   → هر اجرا       → نگهداری 7 مورد
Weekly  → یکشنبه‌ها     → نگهداری 4 مورد
Monthly → روز اول ماه   → نگهداری 12 مورد
```

Daily Backup با `tar.gz` ساخته می‌شود و Weekly/Monthly به جای ساخت Archive مجدد، با Hard Link به Backup روزانه همان زمان اشاره می‌کنند.

قبل از Backup، وجود Source و فضای آزاد دیسک بررسی می‌شود و در پایان، Backupهای قدیمی مطابق Retention Policy حذف می‌شوند.

**منبع این مستند:** اسکریپت `backup.sh` ارائه‌شده در این پروژه.
