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

echo "Scaling all dynos to 0 for Heroku app: ${APP_NAME}"
heroku ps:scale web=0 worker=0 -a "${APP_NAME}"
echo "All dynos stopped for ${APP_NAME}"
