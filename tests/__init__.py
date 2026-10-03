"""Tests must never pick up real search API keys from the developer's ~/.hermes/.env."""

from core import websearch

websearch.ENV_FILE = "/nonexistent/deep-dive-test.env"

from core import cache  # noqa: E402

cache._dir = lambda: None  # no on-disk cache in tests: results must not depend on earlier runs
