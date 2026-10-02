"""Test doubles: a scripted runtime that needs no network and no API key."""

import re
from unittest import mock

from core import engine
from runtime.base import BaseRuntime

# Small, deterministic pipeline settings used by every engine test.
DEFAULT_CONFIG = {
    "ANGLES": 2, "VOTES_PER_CLAIM": 3, "REFUTATIONS_REQUIRED": 2,
    "MAX_FETCH": 4, "MAX_VERIFY_CLAIMS": 5, "MAX_WORKERS": 3,
}


def claim_dict(text, importance="central"):
    return {"claim": text, "quote": f"quote for {text}", "importance": importance}


def verdict(refuted, confidence="high"):
    return {"refuted": refuted, "evidence": "e", "confidence": confidence, "counterSource": ""}


class FakeRuntime(BaseRuntime):
    """Scripted runtime.

    search      {query: [result dicts]} returned by web_search().
    pages       {url: text} returned by web_fetch() (missing -> None).
    extractions {url: extraction dict} returned by the Fetch agent.
    verdicts    {claim text: [verdict-or-None per voter]}; default = all supported.
    llm_search  results the LLM Search agent returns (fallback path).
    synthesis   dict returned by the Synthesize agent (None = failure).
    """

    def __init__(self, search=None, pages=None, extractions=None, verdicts=None,
                 llm_search=None, synthesis=None, angles=None, search_raises=False):
        self.search = search or {}
        self.pages = pages or {}
        self.extractions = extractions or {}
        self.verdicts = verdicts or {}
        self.llm_search = llm_search or {}
        self.synthesis = synthesis
        self.angles = angles or [
            {"label": "A", "query": "query a", "rationale": "r"},
            {"label": "B", "query": "query b", "rationale": "r"},
        ]
        self.search_raises = search_raises
        self.agent_calls = []      # (phase, label)
        self.search_calls = []     # queries sent to web_search()
        self.fetch_calls = []      # urls sent to web_fetch()
        self.logs = []

    # ── BaseRuntime ──
    @property
    def name(self):
        return "fake"

    def setup(self):
        return True

    def web_search(self, query, max_results=6):
        self.search_calls.append(query)
        if self.search_raises:
            raise RuntimeError("search backend down")
        return list(self.search.get(query, []))

    def web_fetch(self, url):
        self.fetch_calls.append(url)
        return self.pages.get(url)

    def run_parallel(self, fn_list, max_workers=3):
        return [fn() for fn in fn_list]

    def log(self, message):
        self.logs.append(message)

    def phase(self, name, detail=""):
        pass

    def agent_call(self, prompt, schema=None, label="", phase=""):
        self.agent_calls.append((phase, label))
        if phase == "Scope":
            return {"question": "q", "summary": "s", "angles": self.angles}
        if phase == "Search":
            query = re.search(r"Query: (.*)", prompt).group(1).strip()
            return {"results": self.llm_search.get(query, [])}
        if phase == "Fetch":
            url = re.search(r"URL: (\S+)", prompt).group(1)
            return self.extractions.get(url)
        if phase == "Verify":
            claim = re.search(r'Claim: "(.*)"', prompt).group(1)
            voter = int(label.split(":", 1)[0][1:])
            votes = self.verdicts.get(claim)
            if votes is None:
                return verdict(False)
            return votes[voter] if voter < len(votes) else None
        if phase == "Synthesize":
            return self.synthesis
        return None

    def count(self, phase):
        return sum(1 for p, _ in self.agent_calls if p == phase)


def search_result(url, title="t", relevance="high"):
    return {"url": url, "title": title, "snippet": "s", "relevance": relevance}


def run_engine(rt, question="why is the sky blue?", **overrides):
    """Run engine.run with small deterministic settings."""
    config = dict(DEFAULT_CONFIG)
    config.update(overrides)
    with mock.patch.multiple(engine, **config):
        return engine.run(question, runtime=rt)


def simple_runtime(claims_by_url, **kwargs):
    """Runtime whose angle A returns every url in claims_by_url via real search.

    claims_by_url: {url: [claim texts]}
    """
    results = [search_result(url) for url in claims_by_url]
    search = {"query a": results, "query b": []}
    pages = {url: f"page text of {url}" for url in claims_by_url}
    extractions = {
        url: {"claims": [claim_dict(c) for c in claims], "sourceQuality": "primary", "publishDate": "2025"}
        for url, claims in claims_by_url.items()
    }
    return FakeRuntime(search=search, pages=pages, extractions=extractions, **kwargs)
