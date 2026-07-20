# Codex Hardening Pass

For OpenAI Build Week, [OpenAI Codex](https://openai.com/index/introducing-codex/) (GPT-5.6-Terra) was run against this repository file-by-file: for each core module, Codex was told to read the file plus `README.md` for context, understand its exact role in the pipeline, and do a genuine engineering pass — not a cosmetic rewrite. Ten files were covered in independent sessions, each restricted to its own file so the diffs stay auditable per-module. Per-file notes are in [`CODEX_CHANGES/`](CODEX_CHANGES/).

## What Codex actually fixed

- **Real concurrency bugs.** `core/parallel.py`'s hand-rolled thread throttle could spawn more threads than `max_workers` and silently dropped worker exceptions. Replaced with a bounded `ThreadPoolExecutor` with ordered results and full traceback logging. The same unbounded-thread pattern was fixed in `runtime/generic.py`, `runtime/hermes.py`, and `runtime/claude_code.py`.
- **A security-relevant fetch gap.** `core/engine.py`'s extractor was previously being handed only URL/title metadata instead of the actual fetched page text, and untrusted source text had no guard against being interpreted as instructions. Direct fetches to local/private-IP targets are now rejected, and only HTTP(S) URLs are accepted anywhere a fetch happens.
- **Fragile JSON parsing.** Every LLM-facing module (`core/agent.py`, `core/engine.py`, `runtime/*.py`) used greedy/naive JSON extraction that accepted truncated or malformed model output. Replaced with decoder-based parsing that requires a complete, schema-valid object before it reaches pipeline logic.
- **Cross-call state leakage in `harness.py`.** `DR_*` environment overrides from one `deep_research()` call could leak into a later call because `core.engine` reads its config at import time. Now isolated with a process lock + temporary environment overlay + module reload per call.
- **Thread-safety in `core/monitor.py`.** Phase/agent status mutation had no locking, so concurrent workers from `parallel.py` could produce duplicate IDs and corrupted progress counts. Now guarded with a re-entrant lock and atomic ID allocation; cost accounting no longer mis-prices every agent as the wrong provider.
- **A dead search backend in `core/web.py`.** DuckDuckGo's Instant Answer API doesn't reliably return ordinary web results — swapped for its HTML result page with a tolerant parser, kept Google Custom Search as configured fallback.
- **`runtime/codex.py`** went from an unimplemented stub to actually detecting and shelling out to a local `codex` CLI when present, with a clean fallback to the generic API runtime when it isn't.

## What Codex did NOT change

Per instructions given to every session: no cosmetic-only rewrites, no public CLI/API signature changes unless a real bug required it (none did — `deep_research()`, `agent()`, `search()`, `fetch()`, `run()` all kept their original signatures), and the multi-platform runtime architecture was left intact.

## New platform adapters

A second Codex pass (same file-by-file, one-session-per-file pattern, using `runtime/codex.py` as the shared template) added eight new platform runtime adapters: `cursor.py`, `gemini.py`, `copilot.py`, `amazon_q.py`, `windsurf.py`, `kimi.py`, `glm.py`, `minimax.py`. Each one detects that platform's local CLI (via an env var override or `PATH` lookup — `gemini`, `q`, `cursor-agent`, `kimi`/`~/.kimi-code/bin/kimi`, `glm`/`zai`, `minimax`, a standalone `copilot` binary or `gh copilot`, `windsurf`), shells the research prompt to it on stdin, and parses JSON from its output — falling back cleanly to the generic DeepSeek API path if no CLI is found or the call fails. On the machine this ran on, three of the eight (`gemini`, `copilot` via `gh`, `kimi`) detected and used real local CLIs during testing, not just the fallback path. Wiring into `runtime/__init__.py`'s registry/auto-detect and `harness.py`'s runtime allowlist was done by hand afterward — see `CODEX_CHANGES/runtime_*.md` for each adapter's note.

## Validation

Every touched file passes `python3 -m py_compile`; the full pipeline was smoke-tested end-to-end via `harness.py` (`Scope -> Search -> Fetch -> Verify -> Synthesize`) after the changes, confirming clean imports and graceful structured-error handling on a live API failure.
