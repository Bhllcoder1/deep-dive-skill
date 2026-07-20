# README accuracy pass and repository cleanup

## Changed

- Rewrote `README.md` as an accuracy-and-completeness pass while preserving its cover image, opening tone, quick-start flow, cost-tier guidance, Python API example, architecture overview, and MIT license section.
- Corrected platform support to enumerate all 14 registered adapters: Hermes, Claude Code, generic, Aider, Codex, Cline, Cursor, Gemini, Copilot, Amazon Q, Windsurf, Kimi, GLM, and MiniMax.
- Documented the actual execution path for each adapter: Codex, Cursor, Gemini, Copilot, Amazon Q, Windsurf, Kimi, GLM, and MiniMax shell out to a local CLI when available; Aider and Cline are generic-only; Claude Code's current bridge emits markers but remains request-only, so it uses the generic fallback for results.
- Updated the architecture tree to list every current `core/` module, every `runtime/` Python module, and both Claude Code JavaScript adapter files.
- Expanded environment documentation to cover all configuration variables and every local-CLI override: `CODEX_CLI`, `CURSOR_CLI`, `GEMINI_CLI`, `COPILOT_CLI`, `AMAZON_Q_CLI`, `WINDSURF_CLI`, `KIMI_CLI`, `GLM_CLI`, and `MINIMAX_CLI`.
- Added a README section linking to `CODEX_CHANGES.md` and `CODEX_CHANGES/`, explaining that OpenAI Codex (GPT-5.6) hardened and extended the project.

## Deleted

- Removed `references/omnigent/`: six copied Omnigent source files. A repository-wide search confirmed that `harness.py`, `core/`, and `runtime/` do not import or reference them; they are not part of the Deep Dive pipeline.
- Removed `references/ai-agent-harness-karsilastirma.md` and `references/github-repo-hazirlama-rehberi.md`: unreferenced Turkish background-research and repository-preparation notes. They are not shipped code, are not linked by the README, and have no pipeline dependency.

The cleanup intentionally left `README.md`, `LICENSE`, `CODEX_CHANGES*`, `core/`, `runtime/`, and `assets/` intact.
