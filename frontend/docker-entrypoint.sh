#!/bin/sh
set -eu

cat > /usr/share/nginx/html/config.js <<EOF
window.APP_RUNTIME_CONFIG = {
  apiBaseUrl: "${API_BASE_URL:-/api}"
};
EOF
