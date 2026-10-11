#!/usr/bin/env bash
# Back up the app database and Grafana state; keeps the last 14 archives.
# Cron (daily 03:00):  0 3 * * * cd ~/dispute-assistant && ./deploy/scripts/backup.sh >> ~/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/../.."
DEST="${BACKUP_DIR:-$HOME/backups}"
mkdir -p "$DEST"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

# SQLite online backup (consistent while the app runs)
docker compose exec -T api python -c "
import sqlite3; src = sqlite3.connect('/data/app.db'); dst = sqlite3.connect('/data/backup.db')
src.backup(dst); dst.close(); src.close()"
docker compose cp api:/data/backup.db "$DEST/app-$STAMP.db"

# Grafana state (dashboards are provisioned from git; this keeps users, alert contact points, annotations)
docker run --rm -v dispute-assistant_grafana_data:/src:ro -v "$DEST":/dst alpine \
  tar czf "/dst/grafana-$STAMP.tgz" -C /src .

ls -1t "$DEST"/app-*.db | tail -n +15 | xargs -r rm --
ls -1t "$DEST"/grafana-*.tgz | tail -n +15 | xargs -r rm --
echo "backup ok: $DEST/app-$STAMP.db"
