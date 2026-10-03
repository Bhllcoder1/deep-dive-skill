"""Single JSON-object extractor for LLM output (fences, prose, trailing text)."""

import json
import re
from typing import Any, Optional

_FENCE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)


def matches_schema(parsed: dict, schema: Optional[dict]) -> bool:
    """Check the only schema subset the pipeline relies on: required keys are present."""
    if not schema:
        return True
    required = schema.get("required", []) if hasattr(schema, "get") else []
    return isinstance(required, list) and all(
        isinstance(name, str) and name in parsed for name in required
    )


def extract_json_object(text: Any, schema: Optional[dict] = None) -> Optional[dict]:
    """Return the first complete JSON *object* found in ``text``, else None.

    Accepts a bare object, an object inside a code fence, or an object embedded in
    prose. Arrays/scalars and truncated objects are never returned. When ``schema``
    lists required keys, objects missing them are skipped.
    """
    if isinstance(text, dict):
        return text if matches_schema(text, schema) else None
    if not isinstance(text, str):
        return None
    text = text.lstrip("﻿").strip()
    if not text:
        return None

    candidates = [text]
    candidates.extend(match.group(1).strip() for match in _FENCE.finditer(text))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and matches_schema(parsed, schema):
            return parsed

        start = candidate.find("{")
        while start >= 0:
            try:
                parsed, _ = decoder.raw_decode(candidate[start:])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and matches_schema(parsed, schema):
                return parsed
            start = candidate.find("{", start + 1)
    return None
