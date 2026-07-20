# Copilot runtime adapter

Added `CopilotRuntime`, mirroring the Codex CLI adapter. It honors `COPILOT_CLI`, prefers a standalone `copilot` executable, falls back to `gh copilot`, and delegates failures to `GenericRuntime`.
