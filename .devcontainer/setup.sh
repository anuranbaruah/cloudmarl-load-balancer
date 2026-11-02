#!/usr/bin/env bash
# Runs once when the codespace is created: random Grafana admin password, and
# Grafana's public codespace URL (without it Grafana rejects requests as "origin not allowed").
set -euo pipefail
if [ ! -f .env ]; then
  cp .env.example .env
  echo "GRAFANA_ADMIN_PASSWORD=$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')" >> .env
  echo "GRAFANA_ROOT_URL=https://${CODESPACE_NAME}-3000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}/" >> .env
fi
