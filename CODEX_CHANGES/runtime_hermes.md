# `runtime/hermes.py`

- Added setup/input validation and reliable DeepSeek endpoint handling, including `LLM_API_BASE`, curl availability, HTTP status/API-error reporting, subprocess timeouts, and safe temporary-file cleanup.
- Replaced greedy JSON extraction with decoder-based object parsing and enforced requested top-level schema fields so malformed model output is rejected.
- Made DuckDuckGo search shell-free, decoded redirect URLs, and constrained fetches to HTTP(S) with redirect protocol restrictions.
- Reworked parallel execution into bounded daemon workers with validation, ordered results, exception logging, a total timeout, and protection against late worker writes after return.
- Fixed Hermes config key discovery, whose prior zero-byte read could never locate a configured DeepSeek key.
