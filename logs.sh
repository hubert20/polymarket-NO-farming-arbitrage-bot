#!/usr/bin/env bash
set -euo pipefail

MODE="pretty"
APP_NAME="${HEROKU_APP_NAME:-}"

if [[ "${1:-}" == "raw" ]]; then
  MODE="raw"
  APP_NAME="${2:-${HEROKU_APP_NAME:-}}"
elif [[ -n "${1:-}" ]]; then
  APP_NAME="${1}"
fi

if [[ -z "${APP_NAME}" ]]; then
  echo "usage: $0 [raw] [heroku-app]  (or set HEROKU_APP_NAME)" >&2
  exit 1
fi

if ! command -v heroku >/dev/null 2>&1; then
  echo "heroku CLI not found in PATH" >&2
  exit 1
fi

if [[ "${MODE}" == "raw" ]]; then
  heroku logs -a "${APP_NAME}" --tail
else
  heroku logs -a "${APP_NAME}" --tail | python3 scripts/parse_logs.py
fi
