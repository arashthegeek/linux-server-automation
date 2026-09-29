#!/bin/bash

# ==============================
# Backup Configuration
# ==============================

SOURCE="/home/admin/Workspace/company"

BACKUP_DIR="$SOURCE/Backup"
DAILY_DIR="$BACKUP_DIR/daily"
WEEKLY_DIR="$BACKUP_DIR/weekly"
MONTHLY_DIR="$BACKUP_DIR/monthly"

LOG_FILE="$SOURCE/Logs/backup.log"

# Retention
DAILY_KEEP=7
WEEKLY_KEEP=4
MONTHLY_KEEP=12

# Minimum free space required in GB
MIN_FREE_GB=1

# ==============================
# Backup Exclusions
# ==============================

EXCLUDE_FILE="$SOURCE/backup/backup.exclude"

# ==============================
# Functions
# ==============================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}


cleanup_old_backups() {

    # Daily
    find "$DAILY_DIR" \
        -type f \
        -name "backup-*.tar.gz" \
        -printf '%T@ %p\n' |
        sort -nr |
        tail -n +$((DAILY_KEEP + 1)) |
        cut -d' ' -f2- |
        xargs -r rm -f


    # Weekly
    find "$WEEKLY_DIR" \
        -type f \
        -name "backup-week-*.tar.gz" \
        -printf '%T@ %p\n' |
        sort -nr |
        tail -n +$((WEEKLY_KEEP + 1)) |
        cut -d' ' -f2- |
        xargs -r rm -f


    # Monthly
    find "$MONTHLY_DIR" \
        -type f \
        -name "backup-month-*.tar.gz" \
        -printf '%T@ %p\n' |
        sort -nr |
        tail -n +$((MONTHLY_KEEP + 1)) |
        cut -d' ' -f2- |
        xargs -r rm -f
}


# ==============================
# Prepare directories
# ==============================

mkdir -p "$DAILY_DIR"
mkdir -p "$WEEKLY_DIR"
mkdir -p "$MONTHLY_DIR"

touch "$LOG_FILE"


# ==============================
# Start
# ==============================

log "========== Backup started =========="

DATE=$(date '+%Y-%m-%d')
MONTH=$(date '+%Y-%m')
DAY=$(date '+%u')
DAY_OF_MONTH=$(date '+%d')


# ==============================
# Check source
# ==============================

if [ ! -d "$SOURCE" ]; then
    log "ERROR: Source directory does not exist: $SOURCE"
    exit 1
fi


# ==============================
# Check disk space
# ==============================

FREE_GB=$(df -BG "$BACKUP_DIR" | awk 'NR==2 {gsub("G","",$4); print $4}')

if [ "$FREE_GB" -lt "$MIN_FREE_GB" ]; then
    log "ERROR: Not enough disk space. Free: ${FREE_GB}GB"
    exit 1
fi

log "Free disk space: ${FREE_GB}GB"


# ==============================
# Daily Backup
# ==============================

DAILY_BACKUP="$DAILY_DIR/backup-$DATE.tar.gz"

log "Creating daily backup..."

if tar \
    --exclude-from="$EXCLUDE_FILE" \
    -czf "$DAILY_BACKUP" \
    -C "$(dirname "$SOURCE")" \
    "$(basename "$SOURCE")" \
    2>>"$LOG_FILE"
then

    SIZE=$(du -h "$DAILY_BACKUP" | cut -f1)

    log "Daily backup successful: $DAILY_BACKUP ($SIZE)"

else

    log "ERROR: Daily backup failed"

    rm -f "$DAILY_BACKUP"

    exit 1
fi

# ==============================
# Weekly Backup
# Sunday = 7
# ==============================

if [ "$DAY" -eq 7 ]; then

    WEEKLY_BACKUP="$WEEKLY_DIR/backup-week-$DATE.tar.gz"

    log "Creating weekly backup..."

    if ln "$DAILY_BACKUP" "$WEEKLY_BACKUP" 2>> "$LOG_FILE"; then

        log "Weekly backup successful: $WEEKLY_BACKUP"
	log "Weekly backup uses hard link"

    else

        log "ERROR: Weekly backup failed"

        exit 1
    fi

fi


# ==============================
# Monthly Backup
# First day of month
# ==============================

if [ "$DAY_OF_MONTH" -eq "01" ]; then

    MONTHLY_BACKUP="$MONTHLY_DIR/backup-month-$MONTH.tar.gz"

    log "Creating monthly backup..."

    if ln "$DAILY_BACKUP" "$MONTHLY_BACKUP" 2>> "$LOG_FILE"; then

        log "Monthly backup successful: $MONTHLY_BACKUP"
	log "Weekly backup uses hard link"

    else

        log "ERROR: Monthly backup failed"

        exit 1
    fi

fi


# ==============================
# Cleanup
# ==============================

log "Cleaning old backups..."

cleanup_old_backups

log "Old backups cleanup completed."


# ==============================
# Finish
# ==============================

log "========== Backup finished successfully =========="

exit 0
