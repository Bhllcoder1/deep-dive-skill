# GLM runtime adapter

Added `runtime/glm.py`, a GLM Code adapter that resolves `GLM_CLI`, then `glm`, then `zai`; it uses the CLI with stdin JSON extraction and falls back to the generic runtime on failure.
