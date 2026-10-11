#!/usr/bin/env bash
# Restore the app database from a backup file.   ./deploy/scripts/restore.sh ~/backups/app-<stamp>.db
set -euo pipefail
cd "$(dirname "$0")/../.."
FILE="${1:?usage: restore.sh <backup.db>}"
docker compose stop api
docker compose cp "$FILE" api:/data/app.db
docker compose start api
echo "restored $FILE; check: docker compose logs -f api"
