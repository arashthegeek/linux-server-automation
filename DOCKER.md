# Docker integration

This integration containerizes the existing **Company Logger** as a one-shot
collector. It does not containerize or replace the host's SSH server, journald,
auditd, backup jobs, or systemd.

## Architecture

- Host `sshd`, `systemd-journald`, and `auditd` continue producing events.
- The logger container reads the host journal and audit log through read-only
  mounts and writes log files/checkpoints under the repository's `company/`
  directory.
- Docker Compose builds and runs the collector.
- An optional host systemd oneshot unit and timer run the container periodically.

## Requirements

- Debian 12 or another Linux host using Docker Engine and the Compose plugin.
- Host SSH logging in journald.
- Host auditd rules configured for the project's watched keys.
- Host paths `/var/log/journal`, `/run/log/journal`, `/etc/machine-id`,
  and `/var/log/audit/audit.log` must exist. Compose deliberately refuses to
  create missing host source paths.
- Run commands from the repository root.

If your host stores journal or audit data at different paths, edit the bind mounts
in `compose.yaml`. If persistent journaling is disabled, older journal entries
may be lost after reboot.

## Run once

Create the output directory if it does not exist, then build and run:

```bash
mkdir -p company/Logs
docker compose build
docker compose run --rm company-logger
```

Inspect the output:

```bash
ls -l company/Logs
tail -n 50 company/Logs/auth.log
tail -n 50 company/Logs/error.log
```

## Run on a schedule with host systemd

The supplied unit assumes the repository is checked out at
`/home/admin/Workspace/linux-server-automation`. If your checkout is elsewhere,
change `WorkingDirectory` and `ConditionPathExists` in
`systemd/company-logger-docker.service` to the actual absolute path.

Install and enable the timer:

```bash
sudo cp systemd/company-logger-docker.service /etc/systemd/system/
sudo cp systemd/company-logger-docker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now company-logger-docker.timer
systemctl list-timers company-logger-docker.timer
```

Check one run and its logs:

```bash
sudo systemctl start company-logger-docker.service
sudo systemctl status company-logger-docker.service
sudo journalctl -u company-logger-docker.service -n 100 --no-pager
```

The timer runs two minutes after boot and then every five minutes. Adjust
`OnUnitActiveSec` if you prefer another interval. Do not enable this timer at the
same time as the existing native logger timer, or the collectors may process the
same events concurrently and race over their checkpoint/cursor files.

## Important limitations

- The logger currently uses the fixed project path
  `/home/admin/Workspace/company`; Compose mounts `./company` there to preserve
  its existing behavior.
- The logger's `/proc` metrics describe the container's view, not the whole host.
  Host-wide CPU, memory, process, and network monitoring needs a separate, carefully
  scoped host metrics design.
- The container runs as root *inside its namespace* so it can read root-owned host
  log files and write project state. It drops Linux capabilities and has no
  privileged mode, but host log data is sensitive; keep output files restricted.
- The collector is a batch job and exits after one pass. It is not a long-running
  daemon, so periodic execution is handled by systemd.
- Review the host's audit rules and SSH journal source before relying on this for
  security monitoring. This Docker setup does not install audit rules or enable
  persistent journaling automatically.
