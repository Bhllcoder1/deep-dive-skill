# MiniMax runtime adapter

Added `runtime/minimax.py`, a MiniMax Code CLI adapter patterned after the Codex runtime. It honors `MINIMAX_CLI`, falls back to `minimax` on `PATH`, parses CLI JSON output, and uses the generic runtime if the CLI is unavailable or fails.
