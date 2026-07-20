# Kimi runtime adapter

Added `runtime/kimi.py`, a Kimi Code CLI adapter that resolves `KIMI_CLI`, `kimi` on `PATH`, and `~/.kimi-code/bin/kimi`, then falls back to `GenericRuntime` when needed.
