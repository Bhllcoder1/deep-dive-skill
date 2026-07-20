# Deep Dive Skill

**Deep Dive** is a universal, adversarially-verified deep research agent that runs as a portable *skill* on top of any AI coding/agent platform — Hermes, Claude Code, Aider, Codex CLI, Cline, or plain Python. Point it at a question; it comes back with a claim-by-claim, source-cited report where every claim has survived independent cross-examination before it's allowed into the final answer.

```
Pipeline: Scope → Search → Fetch → Verify (Adversarial) → Synthesize
```

## Why it's different

Most "research agents" just summarize whatever the first few search results say. Deep Dive treats every extracted claim as guilty until proven innocent: each claim is independently re-checked by 2–3 verifier agents, and only claims that survive the majority vote make it into the report. This kills the single most common failure mode of LLM research — confidently repeating a marketing claim or a stale/wrong source as fact.

It also isn't locked to one platform. The same pipeline (`core/`) runs identically whether the underlying agent runtime is Hermes's `delegate_task`, Claude Code's built-in `agent()`/`WebSearch`, or a plain Python/DeepSeek fallback with zero dependencies — the runtime is auto-detected and swapped out transparently (`runtime/`).

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/deep-dive-skill.git
cd deep-dive-skill

# 2. Set API key
export DEEPSEEK_API_KEY="sk-..."

# 3. Run research
python3 harness.py "Compare Storj vs Filebase decentralized storage"
```

## Features

- **Multi-platform** — auto-detects runtime (Hermes, Claude Code, Aider, Codex, generic)
- **Adversarial verification** — each claim checked by 2-3 independent verifiers
- **Structured output** — JSON or text report with confidence ratings
- **Configurable** — max sources, claims, votes via env vars or CLI flags
- **Zero dependencies** — works with just Python 3 + curl (requests optional)
- **Live TUI dashboard** — `panel.sh` gives you a control panel to launch, watch, and browse past runs

## Platform Support

| Platform | Auto-detect | Parallel | Web Search | Status |
|----------|-------------|----------|------------|--------|
| Hermes Agent | ✅ | ✅ delegate_task | ✅ built-in | ✅ Active |
| Claude Code | ✅ | ✅ parallel() | ✅ WebSearch | ✅ Active |
| Generic (Python) | ✅ | ✅ threading | ✅ DDG/Google/curl | ✅ Active |
| Aider | ⚠️ Manual | ⚠️ Sequential | ❌ (uses generic) | 🟡 Beta |
| Codex CLI | ⚠️ Manual | ⚠️ Sequential | ❌ (uses generic) | 🟡 Beta |
| OpenClaw | 🚧 | 🚧 | 🚧 | 🔄 Planned |
| Cline/Roo | 🚧 | 🚧 | 🚧 | 🔄 Planned |
| Chat platforms (ChatGPT, GLM) | ❌ N/A | ❌ N/A | ❌ N/A | ⬜ Not applicable |

> **Not:** Claude Code'un `parallel()`, `WebSearch`, `agent()` built-in fonksiyonları Claude Pro/Enterprise üyeliği gerektirir.
> Üyeliği olmayanlar otomatik olarak `generic` runtime'a düşer (Python threading + DeepSeek API ile paralel çalışır, ücretsiz).

## CLI Usage

```bash
# Basic research
python3 harness.py "What are the pros and cons of Rust vs Go for CLI tools?"

# JSON output
python3 harness.py "..." --format json

# More thorough research
python3 harness.py "..." --max-fetch 20 --max-claims 15 --votes 3

# Force a specific runtime
DR_RUNTIME=generic python3 harness.py "..."

# Save to custom file
python3 harness.py "..." > my-report.json

# Live control panel
./panel.sh
./panel.sh "araştırma sorusu"   # pipeline + panel together
```

## Cost Tiers

Instead of tuning individual knobs, pick a tier — it bounds total agent calls so a run
never silently spawns hundreds of agents:

```bash
python3 harness.py "..." --tier low       # quick sanity check
python3 harness.py "..." --tier medium    # decent coverage, light verification
python3 harness.py "..." --tier high      # default — thorough, adversarially verified
python3 harness.py "..." --tier ultra     # deep, wide research
DR_COST_TIER=ultra python3 harness.py "..."
```

Total agent calls ≈ `2 (scope+synthesize) + angles + max_fetch + (max_verify_claims × votes_per_claim)`.
`max_workers` separately caps how many of those run *concurrently* (hard ceiling: 20, regardless of tier).

| Tier | Angles | Max Fetch | Max Verify Claims | Votes/Claim | Max Concurrent Workers | ~Agent Calls | ~Cost (DeepSeek) |
|------|--------|-----------|--------------------|-------------|--------------------------|--------------|------------------|
| `low`    | 2  | 3  | 2  | 1 | 2  | ~9   | ~$0.02 |
| `medium` | 4  | 8  | 6  | 2 | 4  | ~26  | ~$0.07 |
| `high` *(default)* | 5 | 15 | 12 | 2 | 6 | ~46 | ~$0.12 |
| `ultra`  | 10 | 30 | 35 | 3 | 10 | ~147 | ~$0.35 |

Any individual `DR_*` env var below overrides its tier value explicitly, so you can start
from a tier and tweak just one knob (e.g. `--tier medium --votes 3`).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | **Required.** DeepSeek API key |
| `LLM_API_BASE` | https://api.deepseek.com/v1 | API base URL (OpenAI-compatible) |
| `LLM_MODEL` | deepseek-chat | Model name |
| `DR_RUNTIME` | auto | Force runtime: hermes, claude_code, generic |
| `DR_COST_TIER` | high | Cost tier: low, medium, high, ultra (see above) |
| `DR_ANGLES` | *(tier)* | Number of parallel search angles in Scope phase |
| `DR_MAX_FETCH` | *(tier)* | Max URLs to fetch |
| `DR_MAX_VERIFY_CLAIMS` | *(tier)* | Max claims to verify (most expensive phase) |
| `DR_VOTES_PER_CLAIM` | *(tier)* | Verifier votes per claim (3 = more thorough) |
| `DR_REFUTATIONS_REQUIRED` | *(tier)* | Votes to kill a claim |
| `DR_MAX_WORKERS` | *(tier)* | Max concurrent verifier agents (hard-capped at 20) |
| `GOOGLE_API_KEY` | — | Google Custom Search (fallback) |
| `GOOGLE_CX` | — | Google Custom Search engine ID |
| `SearXNG_URL` | — | Self-hosted SearXNG instance URL |

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

# Access structured data
for finding in result["findings"]:
    print(f"{finding['claim']} — {finding['confidence']}")
    print(f"  Sources: {', '.join(finding['sources'])}")
```

## Architecture

```
harness.py                          ← CLI + Python API
core/
  agent.py                          ← Universal agent() (LLM + schema)
  engine.py                         ← Pipeline: Scope→Search→Fetch→Verify→Synthesize
  parallel.py                       ← pipeline() + parallel() (threading)
  schemas.py                        ← JSON schemas (same as Claude Code)
  web.py                            ← WebSearch + WebFetch (multi-backend)
  dashboard.py                      ← Live TUI control panel
runtime/
  __init__.py                       ← Auto-detect platform
  hermes.py                         ← Hermes Agent adapter
  claude_code.py                    ← Claude Code adapter (stdout markers)
  generic.py                        ← Generic Python adapter (requests/curl)
  aider.py / codex.py / cline.py    ← Beta adapters for other CLIs
  adapters/                         ← Platform-specific integrations
panel.sh                            ← Control panel launcher
```

## How It Works

1. **Scope** — LLM decomposes your question into 5 complementary search angles
2. **Search** — Each angle is searched independently (parallel when possible)
3. **Fetch** — URLs are fetched, deduplicated, and claims extracted with quotes
4. **Verify** — Each claim is adversarially tested by 2-3 independent verifiers
5. **Synthesize** — Surviving claims are merged, ranked, and presented as a report

Claims that survive ≥2/3 refutation votes are included. This prevents false/marketing claims from reaching the final report.

## License

MIT
