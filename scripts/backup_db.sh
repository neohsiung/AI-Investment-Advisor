#!/bin/bash
# Nightly database backup for AI Investment Advisor / AI Investment Advisor 每晚資料庫備份
#
# Crontab (use THIS checkout's absolute path; cron has a minimal PATH so the script sets its own):
# 建議 crontab（用這份 checkout 的絕對路徑；cron 的 PATH 很短，所以腳本自己設定）：
#   0 3 * * * /Users/neohsiung/Work/Projects/investment-advisor/scripts/backup_db.sh >> /Users/neohsiung/Work/Projects/investment-advisor/backups/backup.log 2>&1
#
# A failed or empty dump is never kept and never reported as success: the script exits non-zero and leaves
# backups/BACKUP_FAILED (reason inside); a good run removes that marker. Before 2026-10-21 cron ran with no PATH, so
# `docker` was not found and 29 of 30 nightly files were 0 bytes.
# 失敗或空的備份不保留、也不回報成功：腳本以非 0 結束並留下 backups/BACKUP_FAILED（內含原因），成功後移除該標記。
# 2026-10-21 之前 cron 沒有 PATH，找不到 docker，30 份夜間備份有 29 份是 0 位元組。

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "${PROJECT_ROOT}" || exit 1

DB_CONTAINER="${DB_CONTAINER:-advisor_prod_db}"
DB_NAME="${DB_NAME:-advisor_prod}"
DB_USER="${DB_USER:-postgres}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/db_backup_${TIMESTAMP}.sql"
TMP_FILE="${BACKUP_FILE}.partial"
MARKER="${BACKUP_DIR}/BACKUP_FAILED"

mkdir -p "${BACKUP_DIR}"

fail() {
  echo "Backup FAILED: $1"
  rm -f "${TMP_FILE}"
  printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" > "${MARKER}"
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker not found in PATH (${PATH})"

echo "Starting database backup for ${DB_NAME} at ${TIMESTAMP}..."
# No -t: cron has no TTY, and a TTY would add carriage returns to the dump. / 不加 -t：cron 沒有 TTY。
docker exec "${DB_CONTAINER}" pg_dump -U "${DB_USER}" "${DB_NAME}" > "${TMP_FILE}" 2>> "${BACKUP_DIR}/backup.err" \
  || fail "pg_dump exited non-zero"

[ -s "${TMP_FILE}" ] || fail "dump is empty"
tail -n 5 "${TMP_FILE}" | grep -q "PostgreSQL database dump complete" || fail "dump has no completion trailer (truncated?)"

mv "${TMP_FILE}" "${BACKUP_FILE}"
rm -f "${MARKER}"
echo "Backup successful: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"

# Retention: drop the 0-byte files the old cron left behind, and nightly dumps older than KEEP_DAYS.
# 保留策略：清掉舊 cron 留下的 0 位元組檔，以及超過 KEEP_DAYS 天的夜間備份。
find "${BACKUP_DIR}" -maxdepth 1 -name "db_backup_*.sql" -size 0 -delete
find "${BACKUP_DIR}" -maxdepth 1 -name "db_backup_*.sql" -mtime +"${KEEP_DAYS}" -delete
echo "Old backups cleaned up (kept ${KEEP_DAYS} days)."
