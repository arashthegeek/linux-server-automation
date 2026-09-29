# Company Logger

## معرفی

`company-logger` یک لاگر و collector برای لینوکس است که سه منبع اصلی فعالیت سیستم را جمع‌آوری و در فایل‌های لاگ مجزا ثبت می‌کند:

1. رویدادهای فایل‌سیستم و `auditd` از طریق `ausearch`
2. رویدادهای SSH از `journald` از طریق `journalctl`
3. snapshot دوره‌ای از وضعیت سیستم، شامل CPU، RAM، load average، دیسک، شبکه، uptime و پردازش‌های فعال

اجرای اصلی برنامه در تابع `main()` انجام می‌شود و هر سه collector را در یک اجرای برنامه فعال می‌کند.

> این مستندات بر اساس پیاده‌سازی موجود در `logger.py` تهیه شده‌اند.

---

## ساختار کلی

```text
logger.py
│
├── Configuration
│   ├── PROJECT_ROOT
│   ├── LOG_DIR
│   ├── STATE_DIR
│   ├── checkpoint / journal cursor
│   ├── audit / journalctl paths
│   ├── system monitor interval
│   ├── watched audit keys
│   └── log files
│
├── Data Structures
│   ├── PathRecord
│   └── AuditEvent
│
├── Filesystem Helpers
│   ├── ensure_directories()
│   ├── log_error()
│   ├── now_string()
│   └── append_log()
│
├── Audit Parsing
│   ├── get_event_identity()
│   ├── get_field()
│   ├── decode_proctitle()
│   └── username_from_auid()
│
├── Audit Event Processing
│   ├── group_records()
│   ├── parse_event()
│   ├── relevant_paths()
│   ├── classify_action()
│   ├── format_event()
│   └── route_event()
│
├── auditd Collector
│   └── run_ausearch()
│
├── System Monitor
│   ├── read_proc_stat()
│   ├── read_cpu_usage()
│   ├── read_memory_usage()
│   ├── read_load_average()
│   ├── read_uptime()
│   ├── read_disk_usage()
│   ├── read_network_bytes()
│   ├── read_process_count()
│   ├── read_top_processes()
│   ├── read_system_monitor_state()
│   ├── write_system_monitor_state()
│   └── collect_system_activity()
│
├── SSH / journald Collector
│   ├── run_journalctl_ssh()
│   ├── journal_timestamp()
│   ├── journal_message()
│   ├── parse_ssh_event()
│   └── collect_ssh_events()
│
└── Main
    └── main()
```

---

## مسیرهای اصلی

مقادیر زیر در ابتدای برنامه تعریف شده‌اند:

| مورد | مقدار |
|---|---|
| ریشه پروژه | `/home/admin/Workspace/company` |
| دایرکتوری لاگ | `/home/admin/Workspace/company/Logs` |
| دایرکتوری state | `/home/admin/Workspace/company/logger` |
| checkpoint مربوط به audit | `logger/audit.checkpoint` |
| cursor مربوط به journald | `logger/journal.cursor` |
| state مانیتور سیستم | `logger/system_monitor.state` |
| `ausearch` | `/usr/sbin/ausearch` |
| `journalctl` | `/usr/bin/journalctl` |

دایرکتوری‌ها و فایل‌های لاگ در صورت نیاز به‌صورت خودکار ایجاد می‌شوند.

---

## فایل‌های خروجی

برنامه فایل‌های زیر را مدیریت می‌کند:

| فایل | کاربرد |
|---|---|
| `access.log` | فعالیت عادی فایل‌سیستم |
| `security.log` | عملیات ناموفق یا دارای خطای دسترسی |
| `backup.log` | فعالیت‌های مرتبط با backup |
| `error.log` | خطاهای داخلی collector |
| `auth.log` | رویدادهای SSH |
| `system.log` | snapshotهای وضعیت سیستم |

تمام این فایل‌ها زیر `LOG_DIR` قرار دارند.

---

# 1. Auditd / Filesystem Collector

## منبع داده

collector فایل‌سیستم از `ausearch` استفاده می‌کند:

```text
/usr/sbin/ausearch
```

دستور با این گزینه‌ها اجرا می‌شود:

```text
--checkpoint <checkpoint-file>
--format raw
```

استفاده از checkpoint باعث می‌شود collector بتواند پردازش رویدادهای audit را از وضعیت قبلی ادامه دهد.

---

## Audit Event

هر رویداد audit با شناسه‌ای بر اساس timestamp و serial شناسایی می‌شود:

```text
<timestamp>:<serial>
```

مثلاً:

```text
1712345678.123:456
```

تابع `group_records()` رکوردهای متعلق به یک event را کنار هم قرار می‌دهد.

رکوردهایی که معمولاً در یک event گروه‌بندی می‌شوند شامل موارد زیر هستند:

- `SYSCALL`
- `CWD`
- `PATH`
- `PROCTITLE`

---

## ساختار `AuditEvent`

ساختار اصلی رویداد audit با `dataclass` تعریف شده است:

```python
AuditEvent
```

فیلدهای مهم آن عبارت‌اند از:

| فیلد | توضیح |
|---|---|
| `event_id` | شناسه یکتای event |
| `timestamp` | timestamp رویداد |
| `auid` | audit user ID |
| `uid` | user ID |
| `euid` | effective user ID |
| `user` | نام کاربر استخراج‌شده از AUID |
| `comm` | نام command/process |
| `exe` | مسیر executable |
| `syscall` | syscall مرتبط |
| `success` | موفق یا ناموفق بودن عملیات |
| `exit_code` | کد خروج syscall |
| `cwd` | working directory |
| `key` | کلید audit rule |
| `paths` | مسیرهای مرتبط با event |
| `raw_records` | رکوردهای خام audit |

---

## Audit Keys تحت نظارت

فقط eventهایی که key آن‌ها در مجموعه زیر قرار داشته باشد پردازش می‌شوند:

```text
company_developers
company_hr
company_finance
company_public
company_backup
```

اگر event مربوط به یکی از این keyها نباشد، `parse_event()` آن را کنار می‌گذارد.

---

# 2. انتخاب مسیرهای مرتبط

تابع `relevant_paths()` مسیرهای موجود در event را فیلتر می‌کند.

قواعد فیلتر:

1. مسیر باید مقدار `name` داشته باشد.
2. مسیرهایی با `nametype=PARENT` نادیده گرفته می‌شوند.
3. مسیر باید داخل `PROJECT_ROOT` قرار داشته باشد.

در نتیجه فقط مسیرهایی که واقعاً به پروژه مربوط هستند برای routing نهایی استفاده می‌شوند.

---

# 3. تشخیص نوع عملیات

تابع `classify_action()` نوع عملیات را تعیین می‌کند.

## خطاها

اگر:

```text
success=no
```

باشد، عملیات ابتدا به‌عنوان عملیات ناموفق بررسی می‌شود.

در برخی حالت‌ها:

| exit code | action |
|---|---|
| `-13` | `PERMISSION_DENIED` |
| `-1` | `OPERATION_NOT_PERMITTED` |
| سایر موارد | `FAILED` |

---

## عملیات مبتنی بر `PATH`

اگر اطلاعات PATH موجود باشد:

| `nametype` | action |
|---|---|
| `CREATE` | `CREATE` |
| `DELETE` | `DELETE` |

---

## تشخیص بر اساس syscall

در صورت نبود اطلاعات کافی از PATH، syscall بررسی می‌شود.

### Rename

```text
rename
renameat
renameat2
```

نتیجه:

```text
RENAME
```

### Create

```text
mkdir
mkdirat
mknod
mknodat
creat
```

نتیجه:

```text
CREATE
```

### Delete

```text
unlink
unlinkat
rmdir
```

نتیجه:

```text
DELETE
```

### Permission Change

```text
chmod
fchmod
fchmodat
```

نتیجه:

```text
PERMISSION_CHANGE
```

### Owner Change

```text
chown
fchown
fchownat
lchown
```

نتیجه:

```text
OWNER_CHANGE
```

### Attribute Change

```text
setxattr
fsetxattr
lsetxattr
removexattr
fremovexattr
lremovexattr
```

نتیجه:

```text
ATTRIBUTE_CHANGE
```

### Modify

```text
write
pwrite
pwrite64
truncate
ftruncate
```

نتیجه:

```text
MODIFY
```

اگر هیچ‌کدام از موارد بالا match نشوند:

```text
ACCESS
```

---

# 4. قالب لاگ فایل‌سیستم

رویدادهای audit در قالب زیر format می‌شوند:

```text
[TIMESTAMP] USER=<user> ACTION=<action> PATH=<path> COMMAND=<command>
```

نمونه:

```text
[2026-09-28 14:20:10] USER=ali ACTION=MODIFY PATH=/home/admin/Workspace/company/app.py COMMAND=vim
```

مقدار command ابتدا از `comm` و در صورت نبود آن از `exe` گرفته می‌شود.

---

# 5. Routing رویدادهای Audit

پس از تشخیص action، رویداد به یکی از لاگ‌ها ارسال می‌شود.

## Security

اگر action یکی از موارد زیر باشد:

```text
PERMISSION_DENIED
OPERATION_NOT_PERMITTED
FAILED
```

رویداد وارد:

```text
security.log
```

می‌شود.

---

## Backup

اگر یکی از شرایط زیر برقرار باشد:

- `event.key == company_backup`
- مسیر شامل `/Backup/` باشد
- مسیر با `/Backup` تمام شود

رویداد وارد:

```text
backup.log
```

می‌شود.

---

## Access

سایر فعالیت‌های عادی فایل‌سیستم وارد:

```text
access.log
```

می‌شوند.

---

# 6. SSH / Journald Collector

برای جمع‌آوری رویدادهای SSH از:

```text
/usr/bin/journalctl
```

استفاده می‌شود.

سرویس مورد بررسی:

```text
ssh
```

خروجی به‌صورت JSON دریافت می‌شود و cursor نیز درخواست می‌شود:

```text
-u ssh
-o json
--no-pager
--show-cursor
```

اگر cursor قبلی موجود باشد، از:

```text
--after-cursor
```

استفاده می‌شود.

این مکانیزم باعث می‌شود eventهای قبلی دوباره پردازش نشوند و collector پس از restart بتواند ادامه دهد.

---

# 7. رویدادهای SSH قابل شناسایی

تابع `parse_ssh_event()` چند نوع event را normalize می‌کند.

## Login موفق

برای پیام‌هایی مانند:

```text
Accepted publickey for ...
Accepted password for ...
```

خروجی به شکل زیر است:

```text
[TIMESTAMP] EVENT=SSH_LOGIN USER=<user> SOURCE=<ip> METHOD=<method>
```

---

## Login ناموفق

برای پیام‌هایی مانند:

```text
Failed password for ...
Failed publickey for ...
```

خروجی:

```text
[TIMESTAMP] EVENT=SSH_LOGIN_FAILED USER=<user> SOURCE=<ip> METHOD=<method>
```

---

## کاربر نامعتبر

برای:

```text
Invalid user ...
```

خروجی:

```text
[TIMESTAMP] EVENT=SSH_INVALID_USER USER=<user> SOURCE=<ip>
```

---

## باز شدن session

برای:

```text
session opened for user ...
```

خروجی:

```text
[TIMESTAMP] EVENT=SSH_SESSION_OPEN USER=<user>
```

---

## بسته شدن session

برای:

```text
session closed for user ...
```

خروجی:

```text
[TIMESTAMP] EVENT=SSH_SESSION_CLOSE USER=<user>
```

---

# 8. State مربوط به SSH

پس از parse موفق batch، جدیدترین cursor در فایل زیر ذخیره می‌شود:

```text
logger/journal.cursor
```

ترتیب کار مهم است:

1. eventها دریافت می‌شوند.
2. eventهای قابل شناسایی parse می‌شوند.
3. eventهای معتبر در `auth.log` نوشته می‌شوند.
4. سپس cursor ذخیره می‌شود.

در نتیجه اگر قبل از ذخیره cursor خطایی رخ دهد، eventها در اجرای بعدی دوباره قابل پردازش خواهند بود و خطر از دست رفتن silent event کاهش می‌یابد.

---

# 9. System Monitor

برنامه علاوه بر audit و SSH، یک snapshot شبیه Task Manager ایجاد می‌کند.

فاصله پیش‌فرض:

```text
30 minutes
```

مقدار:

```python
SYSTEM_MONITOR_INTERVAL = 30 * 60
```

وضعیت آخرین اجرای موفق در:

```text
logger/system_monitor.state
```

ذخیره می‌شود.

---

## CPU

CPU از `/proc/stat` خوانده می‌شود.

تابع:

```python
read_cpu_usage()
```

دو snapshot با فاصله یک ثانیه می‌گیرد و utilization را محاسبه می‌کند.

خروجی به شکل درصد است:

```text
CPU=37.4%
```

---

## RAM

اطلاعات RAM از:

```text
/proc/meminfo
```

خوانده می‌شود.

موارد محاسبه‌شده:

- total
- used
- available
- percentage

در لاگ:

```text
RAM=42.1%(4096MB/9728MB)
```

---

## Load Average

از:

```text
/proc/loadavg
```

مقادیر 1، 5 و 15 دقیقه خوانده می‌شوند.

فرمت لاگ:

```text
LOAD=1.20,0.95,0.80
```

---

## Disk

ظرفیت filesystem مربوط به `PROJECT_ROOT` با `os.statvfs()` بررسی می‌شود.

موارد ثبت‌شده:

- total
- used
- free
- percentage

فرمت:

```text
DISK=63.2%(126.4GB/200.0GB)
```

---

## Network

از:

```text
/proc/net/dev
```

مجموع RX/TX interfaceها خوانده می‌شود.

interface `lo` نادیده گرفته می‌شود.

فرمت:

```text
NET_RX=120.5MB NET_TX=84.2MB
```

---

## Uptime

از:

```text
/proc/uptime
```

خوانده شده و بر حسب ساعت ثبت می‌شود:

```text
UPTIME=142.7h
```

---

## تعداد Processها

دایرکتوری `/proc` بررسی شده و entryهای عددی شمرده می‌شوند.

خروجی:

```text
PROCESSES=184
```

---

## Processهای پرمصرف

تابع `read_top_processes()` یک snapshot سبک از processها ایجاد می‌کند.

برای هر process:

- PID
- state
- CPU ticks
- command

خوانده می‌شود.

تعداد پیش‌فرض:

```text
5 process
```

است.

خروجی نمونه:

```text
[2026-09-28 14:30:00] TOP_PROCESS=1 PID=1234 CPU_TICKS=5000 STATE=S COMMAND=python app.py
```

> این بخش تاریخچه CPU processها نیست، بلکه یک snapshot سبک از `procfs` است.

---

# 10. فرمت `system.log`

ابتدا یک خط `SYSTEM_ACTIVITY` نوشته می‌شود:

```text
[TIMESTAMP] SYSTEM_ACTIVITY CPU=<cpu> RAM=<ram> LOAD=<load> DISK=<disk> NET_RX=<rx> NET_TX=<tx> UPTIME=<uptime> PROCESSES=<count>
```

سپس برای processهای برتر، خطوط `TOP_PROCESS` نوشته می‌شوند.

بسته به در دسترس بودن اطلاعات، بعضی metricها ممکن است در خط `SYSTEM_ACTIVITY` وجود نداشته باشند.

---

# 11. مدیریت خطا

خطاهای داخلی برنامه در:

```text
error.log
```

ثبت می‌شوند.

قالب:

```text
[TIMESTAMP] ERROR=<message>
```

collectorهای اصلی به‌صورت جداگانه در `main()` محافظت شده‌اند:

- Audit collector
- SSH collector
- System monitor

بنابراین خطای یکی از collectorها باعث نمی‌شود اجرای دو بخش دیگر به‌صورت مستقیم متوقف شود.

---

# 12. ترتیب اجرای `main()`

در هر اجرای برنامه:

```text
main()
  │
  ├── ensure_directories()
  │
  ├── Audit Collector
  │   ├── run_ausearch()
  │   ├── group_records()
  │   ├── parse_event()
  │   └── route_event()
  │
  ├── SSH Collector
  │   ├── collect_ssh_events()
  │   └── update journal cursor
  │
  └── System Monitor
      └── collect_system_activity()
```

در پایان، یک summary روی stdout چاپ می‌شود:

```text
company-logger: audit=<count> ssh=<count> system=<count>
```

---

# 13. وابستگی‌ها و پیش‌نیازهای اجرایی

کد از امکانات استاندارد Python و APIهای لینوکس استفاده می‌کند.

کتابخانه‌های Python مورد استفاده:

```text
os
re
pwd
json
subprocess
dataclasses
pathlib
typing
```

علاوه بر Python، محیط اجرا باید این اجزای سیستم را داشته باشد:

```text
/usr/sbin/ausearch
/usr/bin/journalctl
/proc
```

همچنین برای دریافت رویدادهای audit و journald، سطح دسترسی مناسب سیستم ضروری است.

---

# 14. مدل داده و جریان اطلاعات

## Audit

```text
auditd
   │
   ▼
ausearch
   │
   ▼
raw records
   │
   ▼
group_records()
   │
   ▼
parse_event()
   │
   ├── watched key?
   │       │
   │       └── no → ignore
   │
   ▼
relevant_paths()
   │
   ▼
classify_action()
   │
   ▼
format_event()
   │
   ▼
route_event()
   ├── security.log
   ├── backup.log
   └── access.log
```

## SSH

```text
journald
   │
   ▼
journalctl -u ssh
   │
   ▼
JSON entries
   │
   ▼
parse_ssh_event()
   │
   ▼
auth.log
   │
   ▼
journal.cursor
```

## System Monitor

```text
/proc/*
   │
   ├── /proc/stat
   ├── /proc/meminfo
   ├── /proc/loadavg
   ├── /proc/uptime
   ├── /proc/net/dev
   └── /proc/<pid>/*
          │
          ▼
collect_system_activity()
          │
          ▼
system.log
```

---

# 15. نمونه خروجی کلی

پس از اجرای برنامه، ممکن است ساختار لاگ‌ها به شکل زیر باشد:

```text
Logs/
├── access.log
├── security.log
├── backup.log
├── error.log
├── auth.log
└── system.log

logger/
├── audit.checkpoint
├── journal.cursor
└── system_monitor.state
```

نمونه محتوای `access.log`:

```text
[2026-09-28 14:20:10] USER=ali ACTION=MODIFY PATH=/home/admin/Workspace/company/app.py COMMAND=vim
```

نمونه `security.log`:

```text
[2026-09-28 14:21:03] USER=ali ACTION=PERMISSION_DENIED PATH=/home/admin/Workspace/company/secret.txt COMMAND=cat
```

نمونه `auth.log`:

```text
[2026-09-28 14:22:14] EVENT=SSH_LOGIN USER=ali SOURCE=192.168.1.20 METHOD=publickey
```

نمونه `system.log`:

```text
[2026-09-28 14:30:00] SYSTEM_ACTIVITY CPU=18.4% RAM=41.2%(4000MB/9700MB) LOAD=0.80,0.71,0.65 DISK=61.0%(122.0GB/200.0GB) NET_RX=120.5MB NET_TX=84.2MB UPTIME=142.7h PROCESSES=184
[2026-09-28 14:30:00] TOP_PROCESS=1 PID=1234 CPU_TICKS=5000 STATE=S COMMAND=python app.py
```

---

# 16. خلاصه مسئولیت توابع اصلی

| تابع | مسئولیت |
|---|---|
| `ensure_directories()` | ایجاد دایرکتوری‌ها و فایل‌های لاگ |
| `log_error()` | ثبت خطا |
| `append_log()` | append کردن پیام به لاگ |
| `get_event_identity()` | استخراج شناسه audit event |
| `get_field()` | استخراج field از رکورد audit |
| `decode_proctitle()` | decode کردن `PROCTITLE` |
| `username_from_auid()` | تبدیل AUID به username |
| `group_records()` | گروه‌بندی رکوردهای audit |
| `parse_event()` | تبدیل raw audit event به `AuditEvent` |
| `relevant_paths()` | فیلتر مسیرهای پروژه |
| `classify_action()` | تشخیص نوع عملیات |
| `format_event()` | تولید متن استاندارد event |
| `route_event()` | ارسال event به log مناسب |
| `run_ausearch()` | دریافت audit eventهای جدید |
| `read_cpu_usage()` | محاسبه CPU utilization |
| `read_memory_usage()` | خواندن وضعیت RAM |
| `read_load_average()` | خواندن load average |
| `read_disk_usage()` | محاسبه فضای دیسک |
| `read_network_bytes()` | خواندن RX/TX |
| `read_process_count()` | شمارش processها |
| `read_top_processes()` | snapshot پردازش‌های پرمصرف |
| `collect_system_activity()` | تولید snapshot سیستم |
| `run_journalctl_ssh()` | دریافت SSH eventها |
| `parse_ssh_event()` | normalize کردن SSH event |
| `collect_ssh_events()` | ثبت SSH eventها و cursor |
| `main()` | orchestration کل سیستم |

---

## نکات مهم

- پردازش audit فقط برای `WATCHED_KEYS` انجام می‌شود.
- مسیرهای خارج از `PROJECT_ROOT` در routing فایل‌سیستم کنار گذاشته می‌شوند.
- eventهای failed به‌صورت جداگانه در `security.log` قرار می‌گیرند.
- eventهای backup بر اساس audit key یا مسیر backup تشخیص داده می‌شوند.
- SSH eventها با cursor پردازش می‌شوند تا collector restart-safe باشد.
- system monitoring به‌صورت پیش‌فرض هر ۳۰ دقیقه انجام می‌شود.
- CPU برای محاسبه utilization به یک فاصله اندازه‌گیری یک‌ثانیه‌ای نیاز دارد.
- `TOP_PROCESS` یک snapshot است و تاریخچه مصرف CPU ایجاد نمی‌کند.
- خطاهای collectorها در `error.log` ثبت می‌شوند.
- اجرای برنامه با `main()` هر سه collector را پشت سر هم اجرا می‌کند.

