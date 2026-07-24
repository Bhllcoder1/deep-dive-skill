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

The pipeline in `core/` is shared across all runtimes. `runtime/` selects an adapter automatically or via `DR_RUNTIME`; the generic path uses an OpenAI-compatible API plus DuckDuckGo HTML search, optional Google Custom Search, or optional SearXNG.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Bhllcoder1/deep-dive-skill.git
cd deep-dive-skill

# 2. Set an API key for the generic fallback
export DEEPSEEK_API_KEY="sk-..."

# 3. Run research
python3 harness.py "Compare Storj vs Filebase decentralized storage"
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

All 15 adapters are registered in `runtime/__init__.py`. The ten CLI adapters send each agent prompt to the local CLI on standard input, parse JSON from its output, and run those CLI calls in a bounded local worker pool; if the CLI is missing, fails, or returns invalid JSON, they fall back to `GenericRuntime`.

| Platform | Runtime name | Selection | Agent execution path | Search/fetch path |
|----------|--------------|-----------|----------------------|-------------------|
| Hermes Agent | `hermes` | `HERMES_AGENT` or `DR_RUNTIME=hermes` | Hermes runtime; no platform CLI shell-out | Adapter HTTP/curl path |
| Claude Code | `claude_code` | `CLAUDE_CODE=1` or `DR_RUNTIME=claude_code` | Emits bridge markers, then uses the generic API fallback because the bundled bridge is request-only | Emits bridge markers, then curl fallback |
| Generic Python | `generic` | Default or `DR_RUNTIME=generic` | OpenAI-compatible API via `requests` or `curl` | DuckDuckGo HTML; optional Google Custom Search or SearXNG |
| Aider | `aider` | `AIDER_CHAT_MODE`/`AIDER_VERSION` or forced | **Generic-only** (`GenericRuntime`); no Aider CLI shell-out | Generic search/fetch |
| Codex CLI | `codex` | `CODEX_CLI` or forced | Local `codex` CLI, else generic fallback | Generic search/fetch |
| Cline / Roo Code | `cline` | `CLINE_MCP` or forced | **Generic-only** (`GenericRuntime`); no Cline/Roo CLI shell-out | Generic search/fetch; `MCP_WEB_SEARCH_URL` is only reported during setup |
| Cursor Agent | `cursor` | `CURSOR_CLI` or forced | Local `cursor-agent` CLI, else generic fallback | Generic search/fetch |
| Gemini CLI | `gemini` | `GEMINI_CLI` or forced | Local `gemini` CLI, else generic fallback | Generic search/fetch |
| GitHub Copilot | `copilot` | `COPILOT_CLI` or forced | Local `copilot`, then `gh copilot`, else generic fallback | Generic search/fetch |
| Amazon Q Developer | `amazon_q` | `AMAZON_Q_CLI` or forced | Local `q` CLI, else generic fallback | Generic search/fetch |
| Windsurf | `windsurf` | `WINDSURF_CLI` or forced | Local `windsurf` CLI, else generic fallback | Generic search/fetch |
| Kimi Code | `kimi` | `KIMI_CLI` or forced | Local `kimi`, then `~/.kimi-code/bin/kimi`, else generic fallback | Generic search/fetch |
| GLM Code (Z.ai) | `glm` | `GLM_CLI` or forced | Local `glm`, then `zai`, else generic fallback | Generic search/fetch |
| MiniMax Code | `minimax` | `MINIMAX_CLI` or forced | Local `minimax` CLI, else generic fallback | Generic search/fetch |
| Google Antigravity CLI | `antigravity` | `ANTIGRAVITY_CLI` or forced | Local `antigravity` CLI, else generic fallback; its interactive `/agent` and `/agents` commands are not used | Generic search/fetch |

All adapters expose bounded parallel work to the pipeline; `DR_MAX_WORKERS` controls the verifier concurrency and is hard-capped at 20.

## CLI Usage

```bash
# Basic research
python3 harness.py "What are the pros and cons of Rust vs Go for CLI tools?"

# JSON report on stdout (progress goes to stderr)
python3 harness.py "..." --format json

# More thorough research
python3 harness.py "..." --max-fetch 20 --max-claims 15 --votes 3

# Force a specific runtime
python3 harness.py "..." --runtime codex
DR_RUNTIME=generic python3 harness.py "..."

# Save the report to a chosen file
python3 harness.py "..." --output my-report.json

# Live control panel
./panel.sh
./panel.sh "research question"
```

The Python API accepts the same `tier`, `angles`, `max_fetch`, `max_verify_claims`, `votes_per_claim`, `refutations_required`, and `max_workers` settings as keyword arguments. Each `deep_research()` call temporarily applies its settings and restores the process environment afterward.

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
| `DR_RUNTIME` | `auto` | Force one of: `hermes`, `claude_code`, `generic`, `aider`, `codex`, `cline`, `cursor`, `gemini`, `copilot`, `amazon_q`, `windsurf`, `kimi`, `glm`, or `minimax`. |
| `DR_COST_TIER` | `high` | Cost preset: `low`, `medium`, `high`, or `ultra`. |
| `DR_ANGLES` | tier value | Number of search angles. |
| `DR_MAX_FETCH` | tier value | Maximum URLs fetched and claim-extracted. |
| `DR_MAX_VERIFY_CLAIMS` | tier value | Maximum claims sent to adversarial verification. |
| `DR_VOTES_PER_CLAIM` | tier value | Independent verifier calls per selected claim. |
| `DR_REFUTATIONS_REQUIRED` | tier value | Refutation/support threshold; cannot exceed `DR_VOTES_PER_CLAIM`. |
| `DR_MAX_WORKERS` | tier value | Maximum concurrent verifier workers; hard-capped at 20. |
| `GOOGLE_API_KEY` + `GOOGLE_CX` | — | Enable Google Custom Search when DuckDuckGo returns no results. Both are required. |
| `SearXNG_URL` | — | HTTP(S) URL for a self-hosted SearXNG instance; the generic web helper falls back if it is unavailable. |
| `LLM_PROVIDER` | `deepseek` | Dashboard/monitor provider selection. |
| `LLM_API_KEY` | — | Explicit dashboard/monitor API key. |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `KIMI_API_KEY`, `QWEN_API_KEY`, `GEMINI_API_KEY`, `MINIMAX_API_KEY`, `ZHIPU_API_KEY` | — | Provider-specific keys recognized by the dashboard/monitor when `LLM_PROVIDER` selects the corresponding provider. The generic pipeline runtime itself uses `DEEPSEEK_API_KEY`. |
| `MCP_WEB_SEARCH_URL` | — | Reported by the Cline setup message only; it does not replace the generic search implementation. |

### Local CLI overrides

Every CLI-backed adapter accepts a command/path override. The value can be an executable path or a command resolvable on `PATH`; adapters otherwise try their built-in command names listed in the platform table.

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

Auto-detection also recognizes `HERMES_AGENT`, `CLAUDE_CODE=1`, `AIDER_CHAT_MODE` or `AIDER_VERSION`, and `CLINE_MCP`. `OPENCLAW_MODE` is recognized during detection but has no registered OpenClaw adapter, so it resolves to the generic runtime; use an explicitly supported `DR_RUNTIME` value instead.

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
harness.py                          ← CLI and Python API; per-call configuration isolation
panel.sh                            ← Dashboard launcher
assets/
  cover.png                         ← README cover image
core/
  __init__.py                       ← Public core exports
  agent.py                          ← Legacy universal LLM helper and JSON/schema boundary
  dashboard.py                      ← Terminal dashboard, controller, and run history
  engine.py                         ← Scope → Search → Fetch → Verify → Synthesize pipeline
  monitor.py                        ← Thread-safe phase/agent monitoring and cost reporting
  parallel.py                       ← Bounded pipeline/parallel helper functions
  schemas.py                        ← Structured-output schemas
  tiers.py                          ← Cost-tier presets and worker ceiling
  web.py                            ← Portable search and bounded HTTP(S) fetch helpers
runtime/
  __init__.py                       ← Runtime registry, detection, and factory
  base.py                           ← Runtime interface and capability types
  hermes.py                         ← Hermes runtime
  claude_code.py                    ← Claude bridge markers plus generic fallback
  generic.py                        ← OpenAI-compatible API and web fallback runtime
  aider.py                          ← Aider-named generic-only adapter
  cline.py                          ← Cline/Roo-named generic-only adapter
  codex.py                          ← Codex CLI adapter
  cursor.py                         ← Cursor Agent CLI adapter
  gemini.py                         ← Gemini CLI adapter
  copilot.py                        ← Copilot / gh copilot adapter
  amazon_q.py                       ← Amazon Q `q` CLI adapter
  windsurf.py                       ← Windsurf CLI adapter
  kimi.py                           ← Kimi CLI adapter
  glm.py                            ← GLM / zai CLI adapter
  minimax.py                        ← MiniMax CLI adapter
  adapters/
    claude-code-workflow.js         ← Standalone Claude Code workflow implementation
    claude-code-wrapper.js          ← Node wrapper for the Python harness bridge
CODEX_CHANGES.md                    ← Codex hardening and adapter-extension summary
CODEX_CHANGES/                      ← Per-module hardening notes
```

## How It Works

1. **Scope** — the LLM decomposes the question into complementary search angles.
2. **Search** — each angle is searched and results are normalized and deduplicated.
3. **Fetch** — bounded public HTTP(S) sources are fetched; the model extracts quoted, source-linked claims.
4. **Verify** — independent verifier calls try to refute selected claims. A claim survives only when it has enough non-refutation support; ties and failed votes stay unverified.
5. **Synthesize** — only surviving, source-cited claims are merged into the final report.

## Codex Hardening and Extension

This project was hardened and extended with OpenAI Codex (GPT-5.6). [`CODEX_CHANGES.md`](CODEX_CHANGES.md) summarizes the reliability and security work, including bounded concurrency, strict JSON and schema handling, safe fetch behavior, per-call configuration isolation, and the platform-adapter expansion. [`CODEX_CHANGES/`](CODEX_CHANGES/) contains the concise per-module notes.

## License

MIT
