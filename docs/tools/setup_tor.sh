#!/usr/bin/env bash
# Start a local Tor SOCKS proxy so DuckDuckGo (which bot-challenges a plain IP) works for deep-dive.
# Then:  export DR_SEARCH_PROXY=socks5h://127.0.0.1:9050
set -euo pipefail
docker rm -f tor-proxy >/dev/null 2>&1 || true
docker run -d --name tor-proxy --restart unless-stopped -p 127.0.0.1:9050:9050 osminogin/tor-simple >/dev/null
for _ in $(seq 1 60); do
  curl -fs -m 10 --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip 2>/dev/null | grep -q '"IsTor":true' \
    && { echo "Tor up: socks5h://127.0.0.1:9050"; exit 0; }
  sleep 3
done
echo "Tor did not become ready" >&2; exit 1
