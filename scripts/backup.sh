#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/simple-order-pay}"
cd "${APP_DIR}"

if [[ ! -f .env ]]; then
  echo "Missing ${APP_DIR}/.env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups/${STAMP}}"
mkdir -p "${BACKUP_DIR}"

docker compose exec -T mysql sh -c 'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  > "${BACKUP_DIR}/simple_order_pay.sql"

docker compose exec -T backend sh -c 'tar -czf - -C /app/uploads .' \
  > "${BACKUP_DIR}/uploads.tar.gz"

cp .env "${BACKUP_DIR}/env.copy"
chmod 600 "${BACKUP_DIR}/env.copy"

echo "Backup written to ${BACKUP_DIR}"
