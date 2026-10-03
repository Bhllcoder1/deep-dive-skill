"""Tiny on-disk cache (fetched pages, search results) so repeated runs cost no network/time.

DR_CACHE=0 disables; DR_CACHE_DIR overrides ~/.cache/deep-dive; DR_CACHE_TTL seconds (default 6h)."""

import hashlib
import json
import os
import time
from typing import Optional


def _dir() -> Optional[str]:
    if os.environ.get("DR_CACHE", "1") == "0":
        return None
    return os.environ.get("DR_CACHE_DIR") or os.path.expanduser("~/.cache/deep-dive")


def _path(kind: str, key: str) -> Optional[str]:
    base = _dir()
    return os.path.join(base, f"{kind}-{hashlib.sha256(key.encode()).hexdigest()[:32]}.json") if base else None


def get(kind: str, key: str):
    path = _path(kind, key)
    try:
        ttl = float(os.environ.get("DR_CACHE_TTL", "21600"))
        if path and time.time() - os.path.getmtime(path) < ttl:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
    except (OSError, ValueError):
        pass
    return None


def put(kind: str, key: str, value) -> None:
    path = _path(kind, key)
    if not path or not value:
        return
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(value, handle)
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError):
        pass
