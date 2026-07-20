"""
JSON Schemas for structured research output.
Mirrors Claude Code's deep-research workflow schemas exactly.
"""

SCOPE_SCHEMA = {
    "type": "object",
    "required": ["question", "angles", "summary"],
    "properties": {
        "question": {"type": "string"},
        "summary": {"type": "string"},
        "angles": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["label", "query"],
                "properties": {
                    "label": {"type": "string"},
                    "query": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            },
        },
    },
}

SEARCH_SCHEMA = {
    "type": "object",
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["url", "title", "relevance"],
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "snippet": {"type": "string"},
                    "relevance": {"enum": ["high", "medium", "low"]},
                },
            },
        },
    },
}

EXTRACT_SCHEMA = {
    "type": "object",
    "required": ["claims", "sourceQuality"],
    "properties": {
        "sourceQuality": {
            "enum": ["primary", "secondary", "blog", "forum", "unreliable"],
        },
        "publishDate": {"type": "string"},
        "claims": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["claim", "quote", "importance"],
                "properties": {
                    "claim": {"type": "string"},
                    "quote": {"type": "string"},
                    "importance": {"enum": ["central", "supporting", "tangential"]},
                },
            },
        },
    },
}

VERDICT_SCHEMA = {
    "type": "object",
    "required": ["refuted", "evidence", "confidence"],
    "properties": {
        "refuted": {"type": "boolean"},
        "evidence": {"type": "string"},
        "confidence": {"enum": ["high", "medium", "low"]},
        "counterSource": {"type": "string"},
    },
}

REPORT_SCHEMA = {
    "type": "object",
    "required": ["summary", "findings", "caveats"],
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["claim", "confidence", "sources", "evidence"],
                "properties": {
                    "claim": {"type": "string"},
                    "confidence": {"enum": ["high", "medium", "low"]},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "evidence": {"type": "string"},
                    "vote": {"type": "string"},
                },
            },
        },
        "caveats": {"type": "string"},
        "openQuestions": {"type": "array", "items": {"type": "string"}},
    },
}
