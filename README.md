# Deep Dive Skill

<p align="center">
  <img src="assets/cover.png" alt="Deep Dive Skill" width="360">
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-blue.svg">
  <img alt="Platforms" src="https://img.shields.io/badge/runtime%20adapters-15-brightgreen.svg">
  <img alt="Dependencies" src="https://img.shields.io/badge/dependencies-zero%20(stdlib%20%2B%20curl)-lightgrey.svg">
  <img alt="Built with Codex" src="https://img.shields.io/badge/hardened%20with-OpenAI%20Codex%20(GPT--5.6)-412991.svg">
</p>

**Deep Dive** is a universal, adversarially verified deep-research agent that runs as a portable *skill* on top of AI coding and agent platforms. Point it at a question; it returns a claim-by-claim, source-cited report where each accepted claim has survived independent cross-examination.

```
Pipeline: Scope → Search → Fetch → Verify (Adversarial) → Synthesize
```

## Why it's different

Most research agents summarize the first few search results. Deep Dive treats extracted claims as guilty until proven otherwise: independent verifier calls try to refute each claim, and only claims with the required non-refutation support enter the final report. Ties, incomplete votes, malformed model output, and uncited findings remain unverified rather than being presented as facts.

The pipeline in `core/` is shared across all runtimes. `runtime/` selects an adapter automatically or via `DR_RUNTIME`; the generic path uses an OpenAI-compatible API plus DuckDuckGo HTML search, optional Google Custom Search, or optional SearXNG. Every search angle goes to a **real search backend first**; the LLM is asked for URLs only as a logged fallback when the backend returns nothing (`stats.searchFallbacks`, `sources[].via`).

Design notes, the architecture diagrams and the review behind them live in [`docs/`](#documentation).

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Bhllcoder1/deep-dive-skill.git
cd deep-dive-skill

# 2. Set an API key for the generic fallback
export DEEPSEEK_API_KEY="sk-..."

# 3. Run research
python3 harness.py "Compare Storj vs Filebase decentralized storage"

# 4. (Optional) run the offline test suite — no network, no API key
python3 -m unittest discover -s tests -v
```

`requests` is optional. Without it, the generic runtime uses `curl`; if neither is available, it reports the missing client instead of starting a partial run.

## Features

- **15 runtime adapters** — Hermes, Claude Code, generic Python, Aider, Codex, Cline/Roo, Cursor, Gemini, GitHub Copilot, Amazon Q, Windsurf, Kimi, GLM, MiniMax, and Antigravity
- **Adversarial verification** — verifier calls attempt to refute every selected claim; ties and incomplete support are not confirmed
- **Structured output** — JSON or readable text reports with confidence, sources, refuted claims, unverified claims, caveats, and run statistics
- **Configurable scope and cost** — tier presets plus bounded overrides for search angles, fetches, claims, votes, refutations, and concurrency
- **Safe fallbacks** — malformed JSON, bad URLs, failed requests, and failed workers degrade to partial structured results rather than crashing the whole run
- **Live terminal dashboard** — `panel.sh` launches the bundled dashboard

## Platform Support

All 15 adapters are registered in `runtime/__init__.py`. The ten CLI adapters are thin subclasses of one `CliRuntime` base (`runtime/cli.py`): each agent prompt goes to the local CLI in its **headless mode** (per-platform flags, prompt on stdin or as the last argument, never through a shell, run in an empty temp directory), JSON is parsed from its output, and calls run in the shared bounded worker pool; if the CLI is missing, fails (3 failures in a row disable it for the run), or returns invalid JSON, they fall back to `GenericRuntime`. Windsurf, Antigravity, GLM and MiniMax have no known headless agent CLI (`windsurf`/`antigravity` are editor launchers), so they use the generic API unless you set their `*_CLI` override. How each platform was verified: [`docs/PLATFORMS.md`](docs/PLATFORMS.md). Search and fetch always use the generic helpers, so they work without an LLM API key.

| Platform | Runtime name | Selection | Agent execution path | Search/fetch path |
|----------|--------------|-----------|----------------------|-------------------|
| Hermes Agent | `hermes` | `HERMES_AGENT` or `DR_RUNTIME=hermes` | `hermes -z <prompt>` (its own provider, no key needed), else DeepSeek-compatible API | Shared search chain + safe curl fetch |
| Claude Code | `claude_code` | `CLAUDECODE=1` (set by Claude Code), `CLAUDE_CODE=1`, or `DR_RUNTIME=claude_code` | `claude -p` headless (tools off, no session file; opt out with `DR_CLAUDE_HEADLESS=0`), else API fallback; bridge markers are request-only | Shared search chain + safe curl fetch |
| Generic Python | `generic` | Default or `DR_RUNTIME=generic` | OpenAI-compatible API via `requests` or `curl` | DuckDuckGo HTML; optional Google Custom Search or SearXNG |
| Aider | `aider` | `AIDER_CHAT_MODE`/`AIDER_VERSION` or forced | **Generic-only** (`GenericRuntime`); no Aider CLI shell-out | Generic search/fetch |
| Codex CLI | `codex` | `CODEX_CLI` or forced | Local `codex exec -` (read-only sandbox), else generic fallback | Generic search/fetch |
| Cline / Roo Code | `cline` | `CLINE_MCP` or forced | **Generic-only** (`GenericRuntime`); no Cline/Roo CLI shell-out | Generic search/fetch; `MCP_WEB_SEARCH_URL` is only reported during setup |
| Cursor Agent | `cursor` | `CURSOR_CLI` or forced | Local `cursor-agent -p` (unverified), else generic fallback | Generic search/fetch |
| Gemini CLI | `gemini` | `GEMINI_CLI` or forced | Local `gemini -p … -o text` with the prompt on stdin, else generic fallback | Generic search/fetch |
| GitHub Copilot | `copilot` | `COPILOT_CLI` or forced | Local `copilot -p` (unverified; `gh copilot` is not a scriptable agent), else generic fallback | Generic search/fetch |
| Amazon Q Developer | `amazon_q` | `AMAZON_Q_CLI` or forced | Local `q chat --no-interactive` (unverified), else generic fallback | Generic search/fetch |
| Windsurf | `windsurf` | `WINDSURF_CLI` or forced | Generic API (the `windsurf` binary is an editor launcher); `WINDSURF_CLI` can name a headless command | Generic search/fetch |
| Kimi Code | `kimi` | `KIMI_CLI` or forced | Local `kimi -p` (also `~/.kimi-code/bin/kimi`), else generic fallback | Generic search/fetch |
| GLM Code (Z.ai) | `glm` | `GLM_CLI` or forced | Generic API (no known headless GLM CLI); `GLM_CLI` can name one | Generic search/fetch |
| MiniMax Code | `minimax` | `MINIMAX_CLI` or forced | Generic API (no known headless MiniMax CLI); `MINIMAX_CLI` can name one | Generic search/fetch |
| Google Antigravity CLI | `antigravity` | `ANTIGRAVITY_CLI` or forced | Generic API (the `antigravity` binary is a VS Code-style editor launcher and is never run); `ANTIGRAVITY_CLI` can name a headless command | Generic search/fetch |

All adapters expose bounded parallel work to the pipeline; `DR_MAX_WORKERS` controls the verifier concurrency and is hard-capped at 20.

## CLI Usage

```bash
# Basic research
python3 harness.py "What are the pros and cons of Rust vs Go for CLI tools?"

# JSON report on stdout (progress goes to stderr)
python3 harness.py "..." --format json

# More thorough research
python3 harness.py "..." --max-fetch 20 --max-claims 15 --votes 3

# Fine-grained knobs: search angles, refutation threshold, per-phase time budget
python3 harness.py "..." --angles 6 --votes 3 --refutations 2 --phase-budget 600

# Force a specific runtime
python3 harness.py "..." --runtime codex
DR_RUNTIME=generic python3 harness.py "..."

# Save the report to a chosen file
python3 harness.py "..." --output my-report.json

# Live control panel
./panel.sh
./panel.sh "research question"
```

The Python API accepts the same `tier`, `angles`, `max_fetch`, `max_verify_claims`, `votes_per_claim`, `refutations_required`, `max_workers`, and `phase_budget_s` settings as keyword arguments. Each `deep_research()` call builds its own immutable `core.config.Config`; no process-wide state is mutated, so concurrent calls with different settings are safe. Direct users of `core.engine.run()` can pass `config=Config(...)` (default: `Config.from_env()`).

## Cost Tiers

Instead of tuning individual knobs, pick a tier. It bounds total agent calls so a run never silently spawns hundreds of agents:

```bash
python3 harness.py "..." --tier low       # quick sanity check
python3 harness.py "..." --tier medium    # decent coverage, light verification
python3 harness.py "..." --tier high      # default — thorough, adversarially verified
python3 harness.py "..." --tier ultra     # deep, wide research
DR_COST_TIER=ultra python3 harness.py "..."
```

Total agent calls are approximately `2 (scope + synthesize) + angles + max_fetch + (max_verify_claims × votes_per_claim)`. `max_workers` separately caps concurrent verifier calls (hard ceiling: 20).

| Tier | Angles | Max Fetch | Max Verify Claims | Votes/Claim | Refutations Required | Max Concurrent Workers | ~Agent Calls |
|------|--------|-----------|-------------------|-------------|----------------------|------------------------|--------------|
| `low` | 2 | 3 | 2 | 1 | 1 | 2 | ~9 |
| `medium` | 4 | 8 | 6 | 2 | 2 | 4 | ~26 |
| `high` *(default)* | 5 | 15 | 12 | 2 | 2 | 6 | ~46 |
| `ultra` | 10 | 30 | 35 | 3 | 2 | 10 | ~147 |

Any individual `DR_*` setting below overrides its tier value, so you can start from a tier and adjust one bound (for example, `--tier medium --votes 3`). `DR_REFUTATIONS_REQUIRED` cannot exceed `DR_VOTES_PER_CLAIM`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | Required by the generic fallback. The generic and Hermes runtimes also read an exact assignment from `~/.env`; Hermes additionally checks `~/.hermes/config.yaml`. |
| `LLM_API_BASE` | `https://api.deepseek.com/v1` | OpenAI-compatible chat-completions base URL. |
| `LLM_MODEL` | `deepseek-chat` | Model sent to the generic, Hermes, and Claude fallback API paths. |
| `DR_RUNTIME` | `auto` | Force one of: `hermes`, `claude_code`, `generic`, `aider`, `codex`, `cline`, `cursor`, `gemini`, `copilot`, `amazon_q`, `windsurf`, `kimi`, `glm`, `minimax`, or `antigravity`. An unknown name logs a warning and uses `generic`. |
| `DR_COST_TIER` | `high` | Cost preset: `low`, `medium`, `high`, or `ultra`. |
| `DR_ANGLES` | tier value | Number of search angles. |
| `DR_MAX_FETCH` | tier value | Maximum URLs fetched and claim-extracted. |
| `DR_MAX_VERIFY_CLAIMS` | tier value | Maximum claims sent to adversarial verification. |
| `DR_VOTES_PER_CLAIM` | tier value | Independent verifier calls per selected claim. |
| `DR_REFUTATIONS_REQUIRED` | tier value | Refutation/support threshold; cannot exceed `DR_VOTES_PER_CLAIM`. |
| `DR_MAX_WORKERS` | tier value | Maximum concurrent workers for the Search, Fetch and Verify phases; hard-capped at 20. |
| `DR_PHASE_BUDGET` | `900` | Wall-clock seconds per phase; once spent, the phase starts no new work. |
| `DR_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Logs go to stderr; secrets are redacted. |
| `DR_LOG_FORMAT` | `text` | `json` emits one JSON object per line with `ts`, `level`, `logger`, `run_id`, `msg`. |
| `GOOGLE_API_KEY` + `GOOGLE_CX` | — | Enable Google Custom Search when DuckDuckGo returns no results. Both are required. |
| `BRAVE_API_KEY` | — | Optional: Brave Search API, tried before Bing (key goes in a 0600 header file, never argv). |
| `DR_WIKI_LANG` | `en` | Wikipedia language for the keyless last-resort search backend. |
| `DR_CLAUDE_HEADLESS` / `CLAUDE_CLI` | `1` / — | `0` disables the `claude -p` agent channel; `CLAUDE_CLI` overrides its command. |
| `DR_HERMES_CLI` | `1` | `0` disables the `hermes -z` agent channel. |
| `SearXNG_URL` (or `SEARXNG_URL`) | — | HTTP(S) URL of a self-hosted SearXNG instance, queried first by the generic runtime (most dependable option; enable engines that work from your IP, e.g. bing, google, stackoverflow, github). Search chain otherwise: Brave (if `BRAVE_API_KEY`) → Bing HTML → Wikipedia → Google CSE (if configured). **DuckDuckGo is off by default** (its HTML endpoint bot-challenges bursts); `DR_SEARCH_DDG=1` adds it as a last resort. Thin result lists are topped up from keyless vertical APIs (`DR_SEARCH_VERTICALS`, default `stackexchange,hn,openalex`; also `github`, `arxiv`; empty disables). `docs/tools/setup_searxng.sh` starts a local SearXNG with working engines. |
| `DR_SEARCH_PROXY` | — | `socks5h://host:port` (or http/https) proxy for the Bing/DuckDuckGo HTML requests. With it set, DuckDuckGo (blocked on many plain IPs) goes first and works; `docs/tools/setup_tor.sh` starts a local Tor proxy (`socks5h://127.0.0.1:9050`). |
| `TAVILY_API_KEY` / `SERPER_API_KEY` | — | Optional keyed backends (free tiers) tried before Brave. |
| `DR_MAX_PER_DOMAIN` / `DR_EXCERPT_CHARS` | 2 / 6000 | Max fetched pages per site; chars of each page sent to the extractor (query-relevant paragraphs). See `docs/EFFICIENCY.md`. |
| `DR_CACHE` / `DR_CACHE_DIR` / `DR_CACHE_TTL` | on / `~/.cache/deep-dive` / 21600 | On-disk cache of fetched pages and search results (`DR_CACHE=0` disables). |
| `DR_FETCH_JINA` | — | `1` = if a direct fetch returns nothing, retry through r.jina.ai (renders JS pages). Sends the URL to a third party. |
| `LLM_PROVIDER` | `deepseek` | Dashboard/monitor provider selection. |
| `LLM_API_KEY` | — | Explicit dashboard/monitor API key. |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `KIMI_API_KEY`, `QWEN_API_KEY`, `GEMINI_API_KEY`, `MINIMAX_API_KEY`, `ZHIPU_API_KEY` | — | Provider-specific keys recognized by the dashboard/monitor when `LLM_PROVIDER` selects the corresponding provider. The generic pipeline runtime itself uses `DEEPSEEK_API_KEY`. |
| `MCP_WEB_SEARCH_URL` | — | Reported by the Cline setup message only; it does not replace the generic search implementation. |

### Local CLI overrides

Every CLI-backed adapter accepts a command/path override. The value is split with `shlex` and executed **without a shell** (no pipes, redirects or expansion), so it can be an executable path or a command on `PATH`, optionally with arguments. A value that is not an executable (for example `CODEX_CLI=1`, used purely as a detection flag) is ignored and the built-in command names from the platform table are tried instead.

| Variable | Adapter |
|----------|---------|
| `CODEX_CLI` | Codex CLI |
| `CURSOR_CLI` | Cursor Agent |
| `GEMINI_CLI` | Gemini CLI |
| `COPILOT_CLI` | GitHub Copilot |
| `AMAZON_Q_CLI` | Amazon Q Developer |
| `WINDSURF_CLI` | Windsurf |
| `KIMI_CLI` | Kimi Code |
| `GLM_CLI` | GLM Code |
| `MINIMAX_CLI` | MiniMax Code |
| `ANTIGRAVITY_CLI` | Google Antigravity CLI |

Auto-detection also recognizes `HERMES_AGENT`, `CLAUDECODE=1` / `CLAUDE_CODE_ENTRYPOINT` / `CLAUDE_CODE=1`, `AIDER_CHAT_MODE` or `AIDER_VERSION`, and `CLINE_MCP`. (Detection of the old `OPENCLAW_MODE` flag was removed: it never had an adapter and always fell back to the generic runtime.) New adapters are added with one `runtime.register(name, Class, detect_env=...)` call.

## Python API

```python
from harness import deep_research, print_report

result = deep_research(
    "Compare AWS S3 vs Backblaze B2 pricing and hidden fees",
    max_fetch=20,
    max_verify_claims=15,
    votes_per_claim=3,
)

print_report(result)

for finding in result.get("findings", []):
    print(f"{finding['claim']} — {finding['confidence']}")
    print(f"  Sources: {', '.join(finding['sources'])}")
```

## Architecture

```
harness.py                          ← CLI and Python API; builds one immutable Config per call
panel.sh                            ← Dashboard launcher (question passed as argv, never as code)
assets/
  cover.png                         ← README cover image
core/
  __init__.py                       ← Lazy public core exports
  config.py                         ← Immutable Config (strict resolve() / lenient from_env())
  engine.py                         ← Orchestrator: runs PHASES in order, no module-level state
  phases/                           ← One module per phase (NAME + run(ctx, state))
    scope.py  search.py  fetch.py  verify.py  synthesize.py
  context.py                        ← RunContext: contained runtime calls, call counter, budgets, timings
  state.py                          ← RunState flowing through the phases
  prompts.py                        ← Prompt builders (web-derived text is fenced as untrusted)
  validate.py                       ← Validation/normalisation of every model/search response
  results.py                        ← Result builders (success / empty / nothing confirmed / salvage)
  schemas.py                        ← Structured-output schemas
  tiers.py                          ← Cost-tier presets and worker ceiling
  jsonparse.py                      ← The single JSON-object extractor
  urlsafe.py                        ← The single URL-safety gate (lexical + DNS checks)
  safefetch.py                      ← Redirect-checked, IP-pinned curl fetch; HTML→text; secret header files
  websearch.py                      ← The single search chain: Brave (keyed) → Bing HTML → Wikipedia (DuckDuckGo opt-in: throttled, breaker)
  parallel.py                       ← run_bounded(): the one bounded-parallel primitive
  logs.py                           ← logging setup (stderr, secret redaction, JSON option, run id)
  dashboard.py                      ← Terminal dashboard, controller, and run history
  monitor.py                        ← Thread-safe phase/agent monitoring and cost reporting
runtime/
  __init__.py                       ← Runtime registry (register / get_runtime / detect)
  base.py                           ← Runtime interface and capability types
  generic.py                        ← OpenAI-compatible API (retry/backoff) and web fallback runtime
  cli.py                            ← CliRuntime base + the ten local-CLI adapters (Codex, Cursor, Gemini, Copilot, Amazon Q, Windsurf, Kimi, GLM, MiniMax, Antigravity)
  hermes.py                         ← Hermes runtime
  claude_code.py                    ← Claude bridge markers plus generic fallback
  aider.py                          ← Aider-named generic-only adapter
  cline.py                          ← Cline/Roo-named generic-only adapter
  adapters/
    claude-code-workflow.js         ← Standalone Claude Code workflow implementation
    claude-code-wrapper.js          ← Node wrapper for the Python harness bridge
tests/                              ← Offline stdlib unittest suite (fake runtime; no network or API key)
.github/workflows/ci.yml            ← compileall + bash -n panel.sh + unittest on Python 3.9 and 3.12
docs/                               ← Analysis, system-design review, architecture diagrams
CODEX_CHANGES.md                    ← Codex hardening and adapter-extension summary (historical)
CODEX_CHANGES/                      ← Per-module hardening notes (historical)
```

## How It Works

1. **Scope** — the LLM decomposes the question into complementary search angles.
2. **Search** — every angle goes to the runtime's real search backend, in parallel (bounded by `max_workers`). Only if the backend returns nothing is the LLM asked for URLs, and that is logged and counted. Results are normalized, filtered to public http(s) URLs, and deduplicated.
3. **Fetch** — sources are fetched in parallel through the safe fetch path (DNS-checked, redirect-checked); the model extracts quoted, source-linked claims. Quotes that do not occur in the page are flagged to the verifiers.
4. **Verify** — independent verifier calls try to refute selected claims. A claim survives only when it has enough non-refutation support; ties and failed votes stay unverified.
5. **Synthesize** — only surviving, source-cited claims are merged into the final report; if the synthesis cites no confirmed source, the verified claims are returned unmerged (`confirmed`).

Each phase has a wall-clock budget (`--phase-budget`), and `stats` reports the real number of agent calls, per-phase timings and a `runId` that also appears in JSON logs.

## Documentation

- [`docs/PLATFORMS.md`](docs/PLATFORMS.md) — per-platform review of all 15 adapters: headless command, how it was verified, mismatches fixed, remaining gaps
- [`docs/ANALYSIS.md`](docs/ANALYSIS.md) — module responsibilities, README-vs-code differences, findings (missing / redundant), what was fixed and what was removed
- [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) — SOLID / DRY / security / reliability / observability review, applied vs. proposed changes, target architecture
- [`docs/architecture-current.excalidraw`](docs/architecture-current.excalidraw) — architecture as reviewed (baseline), with trust boundaries and violations marked
- [`docs/architecture-target.excalidraw`](docs/architecture-target.excalidraw) — target architecture

Open the `.excalidraw` files at <https://excalidraw.com> (File → Open) or with the VS Code Excalidraw extension. `docs/tools/check_excalidraw.py` validates them (JSON, unique ids, arrow bindings).

## Codex Hardening and Extension

This project was hardened and extended with OpenAI Codex (GPT-5.6). [`CODEX_CHANGES.md`](CODEX_CHANGES.md) summarizes the reliability and security work, including bounded concurrency, strict JSON and schema handling, safe fetch behavior, per-call configuration isolation, and the platform-adapter expansion. [`CODEX_CHANGES/`](CODEX_CHANGES/) contains the concise per-module notes.

## License

MIT
