#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/simple-order-pay}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/conf.d/simple-order-pay.conf}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run deploy.sh as root or with sudo." >&2
  exit 1
fi

for bin in docker nginx; do
  if ! command -v "${bin}" >/dev/null 2>&1; then
    echo "Missing command: ${bin}" >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is required: docker compose" >&2
  exit 1
fi

mkdir -p "${APP_DIR}"

if [[ "${SRC_DIR}" != "${APP_DIR}" ]]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude ".git" \
      --exclude ".env" \
      --exclude "backups" \
      "${SRC_DIR}/" "${APP_DIR}/"
  else
    cp -a "${SRC_DIR}/." "${APP_DIR}/"
  fi
fi

cd "${APP_DIR}"

if [[ ! -f .env ]]; then
  cp .env.example .env
  APP_SECRET_VALUE="$(openssl rand -hex 32 2>/dev/null || date +%s%N | sha256sum | awk '{print $1}')"
  ADMIN_PASSWORD_VALUE="$(openssl rand -hex 18 2>/dev/null || date +%s%N | sha256sum | cut -c1-36)"
  MYSQL_PASSWORD_VALUE="$(openssl rand -hex 18 2>/dev/null || date +%s%N | sha256sum | cut -c1-36)"
  MYSQL_ROOT_PASSWORD_VALUE="$(openssl rand -hex 18 2>/dev/null || date +%s%N | sha256sum | cut -c1-36)"
  sed -i "s/replace_with_64_random_chars/${APP_SECRET_VALUE}/" .env
  sed -i "s/replace_with_a_strong_admin_password/${ADMIN_PASSWORD_VALUE}/" .env
  sed -i "s/replace_with_mysql_user_password/${MYSQL_PASSWORD_VALUE}/" .env
  sed -i "s/replace_with_mysql_root_password/${MYSQL_ROOT_PASSWORD_VALUE}/" .env
  echo "Created ${APP_DIR}/.env with generated secrets. Edit DOMAIN_NAME and PUBLIC_BASE_URL before production use."
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ "${ADMIN_PASSWORD:-}" == "replace_with_a_strong_admin_password" || -z "${ADMIN_PASSWORD:-}" ]]; then
  echo "Refusing to deploy: set a strong ADMIN_PASSWORD in ${APP_DIR}/.env first." >&2
  exit 1
fi

if [[ "${APP_SECRET:-}" == "replace_with_64_random_chars" || -z "${APP_SECRET:-}" ]]; then
  echo "Refusing to deploy: set APP_SECRET in ${APP_DIR}/.env first." >&2
  exit 1
fi

check_port() {
  local port="$1"
  if ss -ltn "( sport = :${port} )" | tail -n +2 | grep -q .; then
    echo "Port ${port} is already listening. Change FRONTEND_HOST_PORT/BACKEND_HOST_PORT in .env." >&2
    ss -ltnp "( sport = :${port} )" || true
    exit 1
  fi
}

echo "Existing simple-order-pay containers, if any:"
docker ps --filter "name=simple-order-pay" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" || true

if ! docker ps --filter "name=simple-order-pay-frontend" --format '{{.Names}}' | grep -q '^simple-order-pay-frontend$'; then
  check_port "${FRONTEND_HOST_PORT:-3001}"
fi
if ! docker ps --filter "name=simple-order-pay-backend" --format '{{.Names}}' | grep -q '^simple-order-pay-backend$'; then
  check_port "${BACKEND_HOST_PORT:-8001}"
fi

docker compose up -d --build

export DOMAIN_NAME="${DOMAIN_NAME:-pay.example.com}"
export CLIENT_MAX_BODY_SIZE="${CLIENT_MAX_BODY_SIZE:-25m}"
export FRONTEND_HOST_PORT="${FRONTEND_HOST_PORT:-3001}"
export BACKEND_HOST_PORT="${BACKEND_HOST_PORT:-8001}"

if [[ -f "${NGINX_CONF}" && "${FORCE_NGINX:-0}" != "1" ]]; then
  echo "Nginx config already exists at ${NGINX_CONF}; leaving it untouched."
  echo "Set FORCE_NGINX=1 to regenerate only this site config."
else
  sed \
    -e "s|\${DOMAIN_NAME}|${DOMAIN_NAME}|g" \
    -e "s|\${CLIENT_MAX_BODY_SIZE}|${CLIENT_MAX_BODY_SIZE}|g" \
    -e "s|\${FRONTEND_HOST_PORT}|${FRONTEND_HOST_PORT}|g" \
    -e "s|\${BACKEND_HOST_PORT}|${BACKEND_HOST_PORT}|g" \
    nginx/simple-order-pay.conf.template > "${NGINX_CONF}"
  nginx -t
  systemctl reload nginx || nginx -s reload
  echo "Installed Nginx site config: ${NGINX_CONF}"
fi

echo "Deploy complete:"
echo "  App dir: ${APP_DIR}"
echo "  Frontend: http://127.0.0.1:${FRONTEND_HOST_PORT:-3001}"
echo "  Backend:  http://127.0.0.1:${BACKEND_HOST_PORT:-8001}/api/health"
echo "  Domain:   ${PUBLIC_BASE_URL:-}"
