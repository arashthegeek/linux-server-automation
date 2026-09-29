#!/usr/bin/env python3

import os
import re
import pwd
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path("/home/admin/Workspace/company")
LOG_DIR = PROJECT_ROOT / "Logs"

STATE_DIR = Path(f"{PROJECT_ROOT}/logger")
CHECKPOINT = STATE_DIR / "audit.checkpoint"
JOURNAL_CURSOR = STATE_DIR / "journal.cursor"

AUSEARCH = "/usr/sbin/ausearch"
JOURNALCTL = "/usr/bin/journalctl"

SYSTEM_MONITOR_LOG = LOG_DIR / "system.log"
SYSTEM_MONITOR_STATE = STATE_DIR / "system_monitor.state"
SYSTEM_MONITOR_INTERVAL = 30 * 60  # 30 minutes

WATCHED_KEYS = {
    "company_developers",
    "company_hr",
    "company_finance",
    "company_public",
    "company_backup",
}

LOG_FILES = {
    "access": LOG_DIR / "access.log",
    "security": LOG_DIR / "security.log",
    "backup": LOG_DIR / "backup.log",
    "error": LOG_DIR / "error.log",
    "auth": LOG_DIR / "auth.log",
    "system": LOG_DIR / "system.log",
}


# ============================================================
# Data structures
# ============================================================

@dataclass
class PathRecord:
    name: str = ""
    nametype: str = ""
    item: str = ""


@dataclass
class AuditEvent:
    event_id: str

    timestamp: str = ""

    auid: str = ""
    uid: str = ""
    euid: str = ""

    user: str = ""

    comm: str = ""
    exe: str = ""

    syscall: str = ""
    success: str = ""
    exit_code: str = ""

    cwd: str = ""
    key: str = ""

    paths: list[PathRecord] = field(default_factory=list)

    raw_records: list[str] = field(default_factory=list)


# ============================================================
# Filesystem helpers
# ============================================================

def ensure_directories():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    for path in LOG_FILES.values():
        path.touch(exist_ok=True)


def log_error(message: str):
    ensure_directories()

    with LOG_FILES["error"].open("a", encoding="utf-8") as f:
        f.write(f"[{now_string()}] ERROR={message}\n")


def now_string():
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_log(log_type: str, message: str):
    path = LOG_FILES[log_type]

    with path.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


# ============================================================
# Parsing helpers
# ============================================================

EVENT_RE = re.compile(
    r'msg=audit\((?P<timestamp>\d+(?:\.\d+)?):(?P<serial>\d+)\)'
)


def get_event_identity(line: str):
    match = EVENT_RE.search(line)

    if not match:
        return None

    timestamp = match.group("timestamp")
    serial = match.group("serial")

    return (
        f"{timestamp}:{serial}",
        timestamp,
        serial,
    )


def get_field(line: str, field_name: str) -> Optional[str]:
    """
    Supports:

        key=value
        key="value"
    """

    pattern = rf'{re.escape(field_name)}=(?:"([^"]*)"|(\S+))'

    match = re.search(pattern, line)

    if not match:
        return None

    return match.group(1) if match.group(1) is not None else match.group(2)


def decode_proctitle(value: str) -> str:
    """
    Audit PROCTITLE is normally hex encoded.
    """

    if not value:
        return ""

    value = value.strip('"')

    try:
        decoded = bytes.fromhex(value).replace(b"\x00", b" ")
        return decoded.decode("utf-8", errors="replace").strip()
    except ValueError:
        return value


def username_from_auid(auid: str) -> str:
    if not auid:
        return "unknown"

    if auid in {"4294967295", "unset", "-1"}:
        return "unset"

    try:
        return pwd.getpwuid(int(auid)).pw_name
    except (ValueError, KeyError):
        return auid


# ============================================================
# Event grouping
# ============================================================

def group_records(output: str):
    """
    Groups:

        SYSCALL
        CWD
        PATH
        PATH
        PROCTITLE

    belonging to the same audit event.
    """

    events = {}

    for line in output.splitlines():

        if not line.strip():
            continue

        identity = get_event_identity(line)

        if identity is None:
            continue

        event_id, timestamp, serial = identity

        if event_id not in events:
            events[event_id] = {
                "timestamp": timestamp,
                "serial": serial,
                "records": [],
            }

        events[event_id]["records"].append(line)

    return events


# ============================================================
# Audit event parser
# ============================================================

def parse_event(event_id: str, data: dict) -> Optional[AuditEvent]:

    event = AuditEvent(
        event_id=event_id,
        timestamp=data["timestamp"],
        raw_records=data["records"],
    )

    for line in data["records"]:

        if line.startswith("type=SYSCALL"):

            event.auid = get_field(line, "auid") or ""
            event.uid = get_field(line, "uid") or ""
            event.euid = get_field(line, "euid") or ""

            event.user = username_from_auid(event.auid)

            event.comm = get_field(line, "comm") or ""
            event.exe = get_field(line, "exe") or ""

            event.syscall = get_field(line, "SYSCALL") or ""

            if not event.syscall:
                event.syscall = get_field(line, "syscall") or ""

            event.success = get_field(line, "success") or ""
            event.exit_code = get_field(line, "exit") or ""

            event.key = get_field(line, "key") or ""

        elif line.startswith("type=CWD"):

            event.cwd = get_field(line, "cwd") or ""

        elif line.startswith("type=PATH"):

            path = PathRecord()

            path.name = get_field(line, "name") or ""
            path.nametype = get_field(line, "nametype") or ""
            path.item = get_field(line, "item") or ""

            event.paths.append(path)

        elif line.startswith("type=PROCTITLE"):

            raw_title = get_field(line, "proctitle") or ""

            decoded = decode_proctitle(raw_title)

            if decoded:
                # comm is usually enough, but decoded proctitle
                # gives us the complete command.
                if not event.comm:
                    event.comm = decoded.split()[0]

    # We only care about our audit rules.
    if event.key not in WATCHED_KEYS:
        return None

    return event


# ============================================================
# Path selection
# ============================================================

def relevant_paths(event: AuditEvent):

    results = []

    for path in event.paths:

        if not path.name:
            continue

        # Ignore the parent directory.
        if path.nametype == "PARENT":
            continue

        # Only paths belonging to our project.
        try:
            Path(path.name).resolve().relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            continue

        results.append(path)

    return results


# ============================================================
# Action detection
# ============================================================

def classify_action(event: AuditEvent, path: Optional[PathRecord]):

    # --------------------------------------------------------
    # Failed operation
    # --------------------------------------------------------

    if event.success == "no":

        try:
            exit_code = int(event.exit_code)

            # Linux errno:
            # EACCES = 13
            # EPERM  = 1
            if exit_code == -13:
                return "PERMISSION_DENIED"

            if exit_code == -1:
                return "OPERATION_NOT_PERMITTED"

        except (ValueError, TypeError):
            pass

        return "FAILED"

    # --------------------------------------------------------
    # PATH nametype is the most reliable source
    # --------------------------------------------------------

    if path:

        if path.nametype == "CREATE":
            return "CREATE"

        if path.nametype == "DELETE":
            return "DELETE"

    # --------------------------------------------------------
    # Syscall fallback
    # --------------------------------------------------------

    syscall = event.syscall.lower()

    if syscall in {
        "rename",
        "renameat",
        "renameat2",
    }:
        return "RENAME"

    if syscall in {
        "mkdir",
        "mkdirat",
        "mknod",
        "mknodat",
        "creat",
    }:
        return "CREATE"

    if syscall in {
        "unlink",
        "unlinkat",
        "rmdir",
    }:
        return "DELETE"

    if syscall in {
        "chmod",
        "fchmod",
        "fchmodat",
    }:
        return "PERMISSION_CHANGE"

    if syscall in {
        "chown",
        "fchown",
        "fchownat",
        "lchown",
    }:
        return "OWNER_CHANGE"

    if syscall in {
        "setxattr",
        "fsetxattr",
        "lsetxattr",
        "removexattr",
        "fremovexattr",
        "lremovexattr",
    }:
        return "ATTRIBUTE_CHANGE"

    if syscall in {
        "write",
        "pwrite",
        "pwrite64",
        "truncate",
        "ftruncate",
    }:
        return "MODIFY"

    return "ACCESS"


# ============================================================
# Event formatting
# ============================================================

def format_timestamp(timestamp: str):

    try:
        import datetime

        dt = datetime.datetime.fromtimestamp(float(timestamp))

        return dt.strftime("%Y-%m-%d %H:%M:%S")

    except Exception:
        return now_string()


def format_event(event: AuditEvent, path: PathRecord, action: str):

    timestamp = format_timestamp(event.timestamp)

    user = event.user or "unknown"

    command = event.comm or event.exe or "unknown"

    path_name = path.name

    return (
        f"[{timestamp}] "
        f"USER={user} "
        f"ACTION={action} "
        f"PATH={path_name} "
        f"COMMAND={command}"
    )


# ============================================================
# Routing
# ============================================================

def route_event(event: AuditEvent):

    paths = relevant_paths(event)

    if not paths:
        return 0

    processed = 0

    for path in paths:

        action = classify_action(event, path)

        message = format_event(
            event,
            path,
            action,
        )

        # Security events
        if action in {
            "PERMISSION_DENIED",
            "OPERATION_NOT_PERMITTED",
            "FAILED",
        }:
            append_log("security", message)

        # Backup events
        elif (
            event.key == "company_backup"
            or "/Backup/" in path.name
            or path.name.endswith("/Backup")
        ):
            append_log("backup", message)

        # Normal filesystem activity
        else:
            append_log("access", message)

        processed += 1

    return processed


# ============================================================
# ausearch
# ============================================================

def run_ausearch():

    command = [
        AUSEARCH,
        "--checkpoint",
        str(CHECKPOINT),
        "--format",
        "raw",
    ]

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    except Exception as exc:

        log_error(f"Failed to execute ausearch: {exc}")

        return ""

    if result.returncode not in (0, 1):

        error = result.stderr.strip()

        if error:
            log_error(
                f"ausearch exited with code "
                f"{result.returncode}: {error}"
            )

    return result.stdout




# ============================================================
# System activity monitor
# ============================================================

def read_proc_stat():
    """
    Read aggregate CPU counters from /proc/stat.
    Returns total CPU time and idle CPU time.
    """

    try:
        with open("/proc/stat", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("cpu "):
                    values = list(map(int, line.split()[1:]))
                    total = sum(values)
                    idle = values[3] + (values[4] if len(values) > 4 else 0)
                    return total, idle
    except (OSError, ValueError):
        pass

    return None, None


def read_cpu_usage():
    """
    Calculate CPU utilization over a short measurement interval.
    """

    total1, idle1 = read_proc_stat()

    if total1 is None:
        return None

    import time
    time.sleep(1)

    total2, idle2 = read_proc_stat()

    if total2 is None:
        return None

    total_delta = total2 - total1
    idle_delta = idle2 - idle1

    if total_delta <= 0:
        return 0.0

    usage = (1.0 - (idle_delta / total_delta)) * 100.0
    return max(0.0, min(100.0, usage))


def read_memory_usage():
    """
    Read RAM statistics from /proc/meminfo.
    """

    values = {}

    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()

                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    try:
                        values[key] = int(parts[1])
                    except ValueError:
                        continue
    except OSError:
        return None

    total_kb = values.get("MemTotal")
    available_kb = values.get("MemAvailable")

    if total_kb is None or available_kb is None:
        return None

    used_kb = total_kb - available_kb
    percent = (used_kb / total_kb) * 100 if total_kb else 0

    return {
        "total_mb": total_kb / 1024,
        "used_mb": used_kb / 1024,
        "available_mb": available_kb / 1024,
        "percent": percent,
    }


def read_load_average():
    """
    Read Linux 1/5/15 minute load averages.
    """

    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            values = f.read().split()

        return {
            "1m": float(values[0]),
            "5m": float(values[1]),
            "15m": float(values[2]),
        }
    except (OSError, ValueError, IndexError):
        return None


def read_uptime():
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def read_disk_usage():
    """
    Disk capacity usage for the project filesystem.
    """

    try:
        usage = os.statvfs(str(PROJECT_ROOT))

        total = usage.f_blocks * usage.f_frsize
        free = usage.f_bavail * usage.f_frsize
        used = total - free

        percent = (used / total) * 100 if total else 0

        return {
            "total_gb": total / (1024 ** 3),
            "used_gb": used / (1024 ** 3),
            "free_gb": free / (1024 ** 3),
            "percent": percent,
        }
    except OSError:
        return None


def read_network_bytes():
    """
    Read cumulative RX/TX bytes from /proc/net/dev.
    """

    rx = 0
    tx = 0

    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue

                interface, data = line.split(":", 1)

                if interface.strip() == "lo":
                    continue

                values = data.split()

                if len(values) >= 9:
                    rx += int(values[0])
                    tx += int(values[8])

    except (OSError, ValueError):
        return None

    return {
        "rx_mb": rx / (1024 ** 2),
        "tx_mb": tx / (1024 ** 2),
    }


def read_process_count():
    """
    Count running processes using /proc.
    """

    try:
        count = 0

        for entry in os.listdir("/proc"):
            if entry.isdigit():
                count += 1

        return count

    except OSError:
        return None


def read_top_processes(limit=5):
    """
    Return the processes consuming the most CPU according to /proc.

    This is a lightweight snapshot rather than a full Task Manager
    process history.
    """

    processes = []

    try:
        pids = [
            entry for entry in os.listdir("/proc")
            if entry.isdigit()
        ]

        for pid in pids:
            try:
                with open(
                    f"/proc/{pid}/stat",
                    "r",
                    encoding="utf-8",
                ) as f:
                    stat = f.read()

                # comm may contain spaces, so find the final ')'.
                close_paren = stat.rfind(")")

                if close_paren == -1:
                    continue

                rest = stat[close_paren + 2:].split()

                # After comm: state is field 3, utime is field 14,
                # stime is field 15 in procfs numbering.
                if len(rest) < 15:
                    continue

                state = rest[0]
                utime = int(rest[11])
                stime = int(rest[12])

                with open(
                    f"/proc/{pid}/cmdline",
                    "rb",
                ) as f:
                    raw_cmdline = f.read()

                cmdline = raw_cmdline.replace(
                    b"\x00",
                    b" ",
                ).decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if not cmdline:
                    cmdline = stat[
                        stat.find("(") + 1:
                        close_paren
                    ]

                processes.append({
                    "pid": pid,
                    "state": state,
                    "cpu_ticks": utime + stime,
                    "command": cmdline[:160],
                })

            except (
                OSError,
                ValueError,
                PermissionError,
            ):
                # Processes can disappear while being inspected.
                continue

    except OSError:
        return []

    processes.sort(
        key=lambda item: item["cpu_ticks"],
        reverse=True,
    )

    return processes[:limit]


def read_system_monitor_state():
    """
    Return the last successful monitor timestamp.
    """

    try:
        return float(
            SYSTEM_MONITOR_STATE.read_text(
                encoding="utf-8"
            ).strip()
        )
    except (
        OSError,
        ValueError,
    ):
        return 0.0


def write_system_monitor_state(timestamp):
    SYSTEM_MONITOR_STATE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    SYSTEM_MONITOR_STATE.write_text(
        str(timestamp),
        encoding="utf-8",
    )


def collect_system_activity(force=False):
    """
    Take a Task-Manager-like system snapshot every 30 minutes.

    The snapshot is stored in system.log.

    Metrics:
      - CPU usage
      - RAM usage
      - load average
      - disk usage
      - network RX/TX counters
      - uptime
      - process count
      - top CPU-consuming processes
    """

    import time

    now = time.time()
    last_run = read_system_monitor_state()

    if not force and last_run and (now - last_run) < SYSTEM_MONITOR_INTERVAL:
        return 0

    cpu = read_cpu_usage()
    memory = read_memory_usage()
    load = read_load_average()
    disk = read_disk_usage()
    network = read_network_bytes()
    uptime = read_uptime()
    process_count = read_process_count()
    top_processes = read_top_processes()

    timestamp = now_string()

    parts = [
        f"[{timestamp}] SYSTEM_ACTIVITY",
    ]

    if cpu is not None:
        parts.append(f"CPU={cpu:.1f}%")

    if memory is not None:
        parts.append(
            f"RAM={memory['percent']:.1f}%"
            f"({memory['used_mb']:.0f}MB/"
            f"{memory['total_mb']:.0f}MB)"
        )

    if load is not None:
        parts.append(
            f"LOAD={load['1m']:.2f},"
            f"{load['5m']:.2f},"
            f"{load['15m']:.2f}"
        )

    if disk is not None:
        parts.append(
            f"DISK={disk['percent']:.1f}%"
            f"({disk['used_gb']:.1f}GB/"
            f"{disk['total_gb']:.1f}GB)"
        )

    if network is not None:
        parts.append(
            f"NET_RX={network['rx_mb']:.1f}MB"
            f" NET_TX={network['tx_mb']:.1f}MB"
        )

    if uptime is not None:
        parts.append(f"UPTIME={uptime / 3600:.1f}h")

    if process_count is not None:
        parts.append(f"PROCESSES={process_count}")

    append_log(
        "system",
        " ".join(parts),
    )

    for index, process in enumerate(
        top_processes,
        start=1,
    ):
        append_log(
            "system",
            (
                f"[{timestamp}] "
                f"TOP_PROCESS={index} "
                f"PID={process['pid']} "
                f"CPU_TICKS={process['cpu_ticks']} "
                f"STATE={process['state']} "
                f"COMMAND={process['command']}"
            ),
        )

    write_system_monitor_state(now)

    return 1


# ============================================================
# SSH / journald
# ============================================================

def run_journalctl_ssh():
    """
    Read SSH events from journald.

    We use JSON output so the journal cursor can be saved reliably.
    This makes the collector restart-safe and avoids processing the
    same journal entries repeatedly.
    """

    command = [
        JOURNALCTL,
        "-u", "ssh",
        "-o", "json",
        "--no-pager",
        "--show-cursor",
    ]

    if JOURNAL_CURSOR.exists():
        cursor = JOURNAL_CURSOR.read_text(
            encoding="utf-8"
        ).strip()

        if cursor:
            command += ["--after-cursor", cursor]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except Exception as exc:
        log_error(f"Failed to execute journalctl: {exc}")
        return [], None

    if result.returncode not in (0, 1):
        error = result.stderr.strip()

        if error:
            log_error(
                f"journalctl exited with code "
                f"{result.returncode}: {error}"
            )

    entries = []
    newest_cursor = None

    for line in result.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        # journalctl --show-cursor prints:
        # -- cursor: s=...
        if line.startswith("-- cursor:"):
            newest_cursor = line[len("-- cursor:"):].strip()
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        entries.append(entry)

    return entries, newest_cursor


def journal_timestamp(entry: dict) -> str:
    """
    Convert __REALTIME_TIMESTAMP (microseconds since epoch)
    to the logger timestamp format.
    """

    try:
        import datetime

        value = int(entry.get("__REALTIME_TIMESTAMP", "0"))

        if value:
            dt = datetime.datetime.fromtimestamp(
                value / 1_000_000
            )

            return dt.strftime("%Y-%m-%d %H:%M:%S")

    except (ValueError, TypeError, OverflowError):
        pass

    return now_string()


def journal_message(entry: dict) -> str:
    """
    Return the MESSAGE field from a journald entry.
    """

    message = entry.get("MESSAGE", "")

    if isinstance(message, list):
        try:
            return bytes(message).decode(
                "utf-8",
                errors="replace",
            )
        except Exception:
            return str(message)

    return str(message)


def parse_ssh_event(entry: dict):
    """
    Normalize common sshd/PAM events into auth.log lines.

    Returns None for unrelated SSH messages.
    """

    message = journal_message(entry)

    if not message:
        return None

    timestamp = journal_timestamp(entry)

    # --------------------------------------------------------
    # Successful login
    #
    # Accepted publickey for ali from 192.168.1.20 port 1234 ssh2
    # Accepted password for ali from 192.168.1.20 port 1234 ssh2
    # --------------------------------------------------------

    match = re.search(
        r"Accepted (\S+) for (\S+) from "
        r"([0-9a-fA-F:.]+)",
        message,
    )

    if match:
        method = match.group(1)
        user = match.group(2)
        source = match.group(3)

        return (
            f"[{timestamp}] "
            f"EVENT=SSH_LOGIN "
            f"USER={user} "
            f"SOURCE={source} "
            f"METHOD={method}"
        )

    # --------------------------------------------------------
    # Failed login
    #
    # Failed password for ali from ...
    # Failed publickey for ali from ...
    # Failed password for invalid user test from ...
    # --------------------------------------------------------

    match = re.search(
        r"Failed (\S+) for "
        r"(?:invalid user )?"
        r"(\S+) from ([0-9a-fA-F:.]+)",
        message,
    )

    if match:
        method = match.group(1)
        user = match.group(2)
        source = match.group(3)

        return (
            f"[{timestamp}] "
            f"EVENT=SSH_LOGIN_FAILED "
            f"USER={user} "
            f"SOURCE={source} "
            f"METHOD={method}"
        )

    # --------------------------------------------------------
    # Invalid user
    # --------------------------------------------------------

    match = re.search(
        r"Invalid user (\S+) from "
        r"([0-9a-fA-F:.]+)",
        message,
    )

    if match:
        user = match.group(1)
        source = match.group(2)

        return (
            f"[{timestamp}] "
            f"EVENT=SSH_INVALID_USER "
            f"USER={user} "
            f"SOURCE={source}"
        )

    # --------------------------------------------------------
    # SSH/PAM session opened
    # --------------------------------------------------------

    match = re.search(
        r"session opened for user (\S+)",
        message,
    )

    if match:
        user = match.group(1)

        return (
            f"[{timestamp}] "
            f"EVENT=SSH_SESSION_OPEN "
            f"USER={user}"
        )

    # --------------------------------------------------------
    # SSH/PAM session closed
    # --------------------------------------------------------

    match = re.search(
        r"session closed for user (\S+)",
        message,
    )

    if match:
        user = match.group(1)

        return (
            f"[{timestamp}] "
            f"EVENT=SSH_SESSION_CLOSE "
            f"USER={user}"
        )

    return None


def collect_ssh_events():
    """
    Collect new SSH events from journald and append normalized
    events to auth.log.
    """

    entries, newest_cursor = run_journalctl_ssh()

    processed = 0

    for entry in entries:
        message = parse_ssh_event(entry)

        if message is None:
            continue

        append_log("auth", message)
        processed += 1

    # Save the cursor only after the batch was successfully parsed.
    # If an exception occurs before this point, the same entries will
    # be retried on the next run instead of being silently lost.
    if newest_cursor:
        JOURNAL_CURSOR.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        JOURNAL_CURSOR.write_text(
            newest_cursor,
            encoding="utf-8",
        )

    return processed


# ============================================================
# Main
# ============================================================

def main():

    ensure_directories()

    # --------------------------------------------------------
    # Filesystem / auditd
    # --------------------------------------------------------

    audit_processed = 0

    try:
        output = run_ausearch()

        if output.strip():
            events = group_records(output)

            for event_id, data in events.items():

                try:
                    event = parse_event(
                        event_id,
                        data,
                    )

                    if event is None:
                        continue

                    audit_processed += route_event(event)

                except Exception as exc:
                    log_error(
                        f"Failed to process audit event "
                        f"{event_id}: {exc}"
                    )

    except Exception as exc:
        log_error(
            f"Audit collector failed: {exc}"
        )

    # --------------------------------------------------------
    # SSH / journald
    # --------------------------------------------------------

    ssh_processed = 0

    try:
        ssh_processed = collect_ssh_events()

    except Exception as exc:
        log_error(
            f"SSH collector failed: {exc}"
        )

    # --------------------------------------------------------
    # Periodic Task-Manager-like system snapshot
    # --------------------------------------------------------

    system_processed = 0

    try:
        system_processed = collect_system_activity()

    except Exception as exc:
        log_error(
            f"System monitor failed: {exc}"
        )

    print(
        f"company-logger: "
        f"audit={audit_processed} "
        f"ssh={ssh_processed} "
        f"system={system_processed}"
    )


if __name__ == "__main__":
    main()
