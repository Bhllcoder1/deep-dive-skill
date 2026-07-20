# `runtime/generic.py` hardening

- Honored `LLM_API_BASE`, validated it, tightened `.env` key parsing, removed API-key prefix logging, and verify curl availability when it is the only HTTP client.
- Added bounded timeouts, subprocess failure reporting, response-shape checks, and resilient JSON-object extraction for both requests and curl LLM calls.
- Added validated DDG search parsing (including nested topics and redirect unwrapping), Google Custom Search fallback when configured, and safe public-HTTP URL filtering.
- Bounded fetched content, rejected unsafe/non-text URLs, validated redirect targets in the requests path, and improved HTML-to-text decoding.
- Replaced the ineffective thread throttling with a capped worker pool that preserves result order, records failures, enforces one overall deadline, and returns a snapshot to avoid post-return mutation races.
