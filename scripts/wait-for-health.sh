#!/usr/bin/env bash
# Poll the readiness endpoint until it returns HTTP 200 (used by CI).
# Usage: scripts/wait-for-health.sh [url] [timeout_seconds]
set -euo pipefail
url="${1:-http://localhost:8000/api/v1/health}"
timeout="${2:-90}"
deadline=$(( $(date +%s) + timeout ))
code=000
while [ "$(date +%s)" -lt "$deadline" ]; do
  code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$url" || true)
  if [ "$code" = "200" ]; then
    echo "Ready: $url"
    exit 0
  fi
  sleep 1
done
echo "Not ready after ${timeout}s: $url (last status: $code)" >&2
exit 1
