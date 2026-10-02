#!/usr/bin/env bash
# Start a local SearXNG for deep-dive (JSON API on 127.0.0.1:8888, engines that work without captchas).
# Usage: docs/tools/setup_searxng.sh   then:  export SEARXNG_URL=http://127.0.0.1:8888
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
data="${SEARXNG_DATA:-$HOME/.deep-dive/searxng}"
mkdir -p "$data"
secret="$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
sed "s/__SECRET__/$secret/" "$here/searxng-settings.yml" > "$data/settings.yml"
docker rm -f searxng >/dev/null 2>&1 || true
docker run -d --name searxng --restart unless-stopped -p 127.0.0.1:8888:8080 \
  -v "$data:/etc/searxng" searxng/searxng >/dev/null
for _ in $(seq 1 30); do
  curl -fs "http://127.0.0.1:8888/search?q=test&format=json" >/dev/null 2>&1 && { echo "SearXNG up: http://127.0.0.1:8888"; exit 0; }
  sleep 1
done
echo "SearXNG did not become ready" >&2; exit 1
