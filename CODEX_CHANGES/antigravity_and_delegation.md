# Antigravity and CLI delegation

Google Antigravity CLI is the Go-based successor to Gemini CLI.  The new
`antigravity` runtime resolves `ANTIGRAVITY_CLI` before looking up the
`antigravity` binary and otherwise keeps the repository's generic fallback.

`runtime/_cli_parallel.py` centralizes bounded, ordered worker execution for
zero-argument callables that each make one local CLI-backed agent call.  It
reuses the hardened worker behavior in `core/parallel.py`: worker failures are
isolated and logged, results retain input order, and worker count is bounded by
`max_workers`.  Every local CLI adapter uses it only when its local CLI is
available; absent CLIs retain `GenericRuntime.run_parallel()` unchanged.

Antigravity's native multi-agent orchestration is intentionally not invoked.
Its `/agent` and `/agents` slash commands live inside an interactive TUI
session; they are not a scriptable non-interactive API reachable by piping one
prompt to stdin and reading one output.  The adapter therefore uses honest
concurrent `antigravity` CLI subprocess calls rather than claiming to drive
native subagents.
