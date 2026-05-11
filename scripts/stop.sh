#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/simple-order-pay}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/conf.d/simple-order-pay.conf}"

cd "${APP_DIR}"

docker compose down

if [[ "${REMOVE_NGINX_CONF:-0}" == "1" && -f "${NGINX_CONF}" ]]; then
  rm -f "${NGINX_CONF}"
  nginx -t
  systemctl reload nginx || nginx -s reload
  echo "Removed Nginx config: ${NGINX_CONF}"
fi

if [[ "${CONFIRM_REMOVE_DATA:-}" == "yes-remove-simple-order-pay-data" ]]; then
  docker volume rm simple-order-pay-mysql-data simple-order-pay-uploads || true
  echo "Removed project Docker volumes."
else
  echo "Project stopped. Data volumes are preserved."
  echo "To remove volumes too, rerun with CONFIRM_REMOVE_DATA=yes-remove-simple-order-pay-data."
fi
