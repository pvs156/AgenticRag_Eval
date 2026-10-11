#!/usr/bin/env bash
# Pull a specific image SHA, restart, health-check, and roll back automatically on failure.
#   ./deploy/scripts/release.sh <git-sha>
set -euo pipefail
cd "$(dirname "$0")/../.."

SHA="${1:?usage: release.sh <git-sha>}"
OWNER="${GHCR_OWNER:?set GHCR_OWNER in the shell profile (lowercase GitHub user/org)}"
STATE=.release
PREV="$(cat "$STATE/current" 2>/dev/null || echo latest)"
mkdir -p "$STATE"

deploy() {
  export API_IMAGE="ghcr.io/$OWNER/dispute-assistant-api:$1"
  export WEB_IMAGE="ghcr.io/$OWNER/dispute-assistant-web:$1"
  docker compose pull api web
  docker compose up -d --remove-orphans
}

healthy() {
  # /readyz turns 200 once the models and vector index are loaded
  for _ in $(seq 1 40); do
    if docker compose exec -T api python -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz').status==200 else 1)" \
      2>/dev/null; then
      return 0
    fi
    sleep 5
  done
  return 1
}

echo "deploying $SHA (previous: $PREV)"
./deploy/scripts/backup.sh || echo "warning: backup failed, continuing"
deploy "$SHA"
if healthy; then
  echo "$SHA" > "$STATE/current"
  echo "$(date -u +%FT%TZ) $SHA" >> "$STATE/history"
  echo "release $SHA healthy"
else
  echo "release $SHA failed health check; rolling back to $PREV" >&2
  deploy "$PREV"
  healthy && echo "rolled back to $PREV" || echo "ROLLBACK ALSO UNHEALTHY: manual action needed" >&2
  exit 1
fi
