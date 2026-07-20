# `core/web.py`

- Replaced DuckDuckGo's Instant Answer API with its HTML result page and a tolerant parser, because the former does not reliably return ordinary web results; normalized redirect URLs and retained Google Custom Search as the configured fallback.
- Validated search inputs, timeouts, SearXNG configuration, and fetch URLs (HTTP(S) only), preventing malformed inputs and shell-sensitive URL handling from reaching backends.
- Hardened HTTP fetching: bounded response size and output length, connect/read timeouts, redirect limits, non-2xx and rate-limit reporting, textual-content checks, charset fallbacks, and resilient malformed-HTML text extraction.
- Reworked curl calls to pass argument lists instead of shell strings, added failure/redirect/timeout/size controls, and fixed the SearXNG path so a configured but unavailable instance falls back to the normal search backend.
- Kept the public `search(query, max_results=6)` and `fetch(url, timeout=30)` signatures unchanged.
