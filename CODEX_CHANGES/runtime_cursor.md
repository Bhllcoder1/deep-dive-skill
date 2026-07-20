# Cursor Runtime Adapter

Added `runtime/cursor.py`, a Cursor Agent CLI adapter that honors `CURSOR_CLI`,
falls back to `cursor-agent` on PATH, and delegates failures to `GenericRuntime`.
