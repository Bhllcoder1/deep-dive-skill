# Amazon Q runtime adapter

Added `runtime/amazon_q.py`, an `AmazonQRuntime` adapter that uses `AMAZON_Q_CLI` or the local `q` CLI and falls back to `GenericRuntime` when unavailable or unsuccessful.
