# `core/agent.py`

- Replaced greedy JSON extraction with decoder-based parsing that accepts only complete objects and rejects truncated nested output; completion results now must satisfy the supplied schema.
- Expanded the built-in schema checks to cover object/array/value types, nested required fields, enums, and item bounds, so malformed or partial LLM data cannot reach pipeline consumers.
- Added boundary validation, response-shape checks, HTTP status handling, bounded retries for transient failures, and explicit connect/read timeouts.
- Hardened the Hermes curl path by shell-quoting credentials, checking failed/invalid responses, honoring the configured model, and always removing the temporary payload file.
- Kept the public `agent(prompt, *, label, phase, schema) -> Optional[dict]` signature unchanged.
