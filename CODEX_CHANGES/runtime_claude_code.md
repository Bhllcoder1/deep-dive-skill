# `runtime/claude_code.py` changes

- Moved Claude bridge markers and adapter progress/log output to stderr. The wrapper reads markers there and stdout must remain valid final JSON.
- Validated marker types/payloads and public inputs (prompts, schemas, search limits, URLs, parallel callables/workers) so malformed calls fail safely.
- Hardened API handling: honors `LLM_API_BASE`, reports non-200/malformed response shapes, handles absent `requests`, and validates required schema fields.
- Replaced greedy JSON extraction with balanced decoder parsing, so fenced/embedded JSON works while partial, concatenated, non-object, or schema-incomplete output is rejected.
- Replaced unbounded daemon threads with a bounded executor that honors `max_workers`, preserves order, and records worker failures.
- Removed shell-based search construction and reject non-HTTP(S) fetch URLs to avoid unsafe or malformed subprocess requests.
- Native Claude markers still use the generic fallback because the existing JS wrapper queues requests but does not provide tool results back to Python; the adapter no longer mistakes marker emission for a result.
