#!/bin/sh
set -eu
cd /app

deps_stamp=node_modules/.kartogram-deps.sha256
if ! sha256sum -c "$deps_stamp" >/dev/null 2>&1; then
  echo 'Synchronizing frontend dependencies with package-lock.json...'
  npm ci --no-audit --no-fund
  sha256sum package.json package-lock.json > "$deps_stamp"
fi

exec "$@"
