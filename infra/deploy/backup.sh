#!/usr/bin/env bash
# Nightly database backup. Keeps 14 days locally; copies to S3 when BACKUP_S3_URI
# is set (for example s3://my-airwatch-backups/db) and the AWS CLI is installed
# with an instance role that may write there.
#
# Install as a cron job on the server:
#   (crontab -l 2>/dev/null; echo "30 20 * * * bash $HOME/airwatch/infra/deploy/backup.sh >> $HOME/airwatch/backups/backup.log 2>&1") | crontab -
#   (20:30 UTC is 02:00 IST, when nobody is using the dashboard.)
#
# Restore:
#   gunzip -c backups/airwatch-<stamp>.sql.gz | docker compose -f infra/docker-compose.prod.yml --env-file .env exec -T db psql -U airwatch -d airwatch
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"
KEEP_DAYS=14
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="backups/airwatch-${STAMP}.sql.gz"

mkdir -p backups
docker compose -f infra/docker-compose.prod.yml --env-file .env exec -T db \
  pg_dump -U airwatch -d airwatch --no-owner | gzip > "$TARGET"
echo "$(date -u +%FT%TZ) wrote $TARGET ($(du -h "$TARGET" | cut -f1))"

find backups -name 'airwatch-*.sql.gz' -mtime +"$KEEP_DAYS" -delete

BACKUP_S3_URI="$(grep -E '^BACKUP_S3_URI=' .env | cut -d= -f2- || true)"
if [ -n "$BACKUP_S3_URI" ] && command -v aws >/dev/null 2>&1; then
  aws s3 cp "$TARGET" "$BACKUP_S3_URI/" --only-show-errors
  echo "copied to $BACKUP_S3_URI"
fi
