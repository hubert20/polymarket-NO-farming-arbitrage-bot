#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:-${HEROKU_APP_NAME:-}}"

if [[ -z "${APP_NAME}" ]]; then
  echo "usage: $0 <heroku-app>  (or set HEROKU_APP_NAME)" >&2
  exit 1
fi

if ! command -v heroku >/dev/null 2>&1; then
  echo "heroku CLI not found in PATH" >&2
  exit 1
fi

echo "Disabling live order transmission for Heroku app: ${APP_NAME}"
heroku config:set LIVE_TRADING_ENABLED=false DRY_RUN=true -a "${APP_NAME}"
echo "Live order transmission disabled for ${APP_NAME}"
