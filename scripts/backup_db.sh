#!/bin/bash
# Database Backup Utility for AI Investment Advisor
# 建議設定 Crontab: 0 3 * * * /path/to/backup_db.sh

# Load environment variables if .env exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

DB_CONTAINER="advisor_prod_db"
DB_NAME="${DB_NAME:-advisor_prod_db}"
DB_USER="${DB_USER:-postgres}"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/db_backup_${TIMESTAMP}.sql"

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

echo "Starting database backup for ${DB_NAME}..."

# Execute pg_dump inside the container
docker exec -t "${DB_CONTAINER}" pg_dump -U "${DB_USER}" "${DB_NAME}" > "${BACKUP_FILE}"

if [ $? -eq 0 ]; then
  echo "Backup successful: ${BACKUP_FILE}"
  # Keep only the last 7 days of backups
  find "${BACKUP_DIR}" -name "db_backup_*.sql" -mtime +7 -delete
  echo "Old backups cleaned up (kept last 7 days)."
else
  echo "Backup FAILED!"
  exit 1
fi
