"""Tests must never pick up real search API keys from the developer's ~/.hermes/.env."""

from core import websearch

websearch.ENV_FILE = "/nonexistent/deep-dive-test.env"
