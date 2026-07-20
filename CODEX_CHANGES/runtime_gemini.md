# Gemini runtime adapter

Added `GeminiRuntime`, which prefers `GEMINI_CLI` or the local `gemini` binary and falls back to `GenericRuntime` when the CLI is unavailable or fails.
