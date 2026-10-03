"""Vertical search APIs: parsing and top-up behaviour, with a fake curl runner (no network)."""

import json
import os
import subprocess
import unittest
from unittest import mock

from core import searchapis, websearch

ARXIV = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1</id>
<title>Ownership
 types</title><summary>About   rust</summary></entry></feed>"""


def runner_returning(body):
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=body if isinstance(body, str) else json.dumps(body), stderr="")
    return run


class VerticalTests(unittest.TestCase):
    def test_stackexchange_hn_openalex_github(self):
        cases = [
            (searchapis.stackexchange_search, {"items": [{"link": "https://stackoverflow.com/q/1", "title": "T", "score": 3}]}),
            (searchapis.hn_search, {"hits": [{"url": None, "objectID": "9", "title": "T", "points": 1}]}),
            (searchapis.openalex_search, {"results": [{"title": "T", "doi": "https://doi.org/10.1/x",
                                                       "abstract_inverted_index": {"b": [1], "a": [0]}}]}),
            (searchapis.github_search, {"items": [{"html_url": "https://github.com/a/b", "full_name": "a/b"}]}),
        ]
        for fn, body in cases:
            with self.subTest(fn=fn.__name__):
                out = fn("q", 3, runner=runner_returning(body))
                self.assertEqual(len(out), 1)
                self.assertTrue(out[0]["url"].startswith("https://"))
        self.assertEqual(searchapis.hn_search("q", 3, runner=runner_returning(
            {"hits": [{"objectID": "9", "title": "T"}]}))[0]["url"], "https://news.ycombinator.com/item?id=9")
        self.assertEqual(searchapis.openalex_search("q", 3, runner=runner_returning(cases[2][1]))[0]["snippet"], "a b")

    def test_malformed_payloads_yield_nothing(self):
        for fn in (searchapis.stackexchange_search, searchapis.hn_search, searchapis.openalex_search,
                   searchapis.github_search, searchapis.arxiv_search):
            self.assertEqual(fn("q", 3, runner=runner_returning("not json {")), [])
            self.assertEqual(fn("q", 3, runner=runner_returning({"items": "x", "hits": 1, "results": None})), [])

    def test_arxiv_parse(self):
        out = searchapis.parse_arxiv(ARXIV, 5)
        self.assertEqual(out[0]["url"], "https://arxiv.org/abs/1")
        self.assertEqual(out[0]["title"], "Ownership types")
        self.assertEqual(searchapis.parse_arxiv("<broken", 5), [])


class TopUpTests(unittest.TestCase):
    def setUp(self):
        self.base = [{"url": "https://a.example/", "title": "a", "snippet": "", "relevance": "high"}]

    def _patched(self, env, **fns):
        return mock.patch.dict(searchapis.VERTICALS, fns, clear=True), mock.patch.dict(os.environ, env)

    def test_tops_up_in_order_without_duplicates_and_stops_at_limit(self):
        calls = []

        def vert(name, urls):
            def fn(q, n, curl_path="curl", runner=None):
                calls.append(name)
                return [{"url": u, "title": u, "snippet": "", "relevance": "low"} for u in urls]
            return fn
        p1, p2 = self._patched({"DR_SEARCH_VERTICALS": "x,y,missing"},
                               x=vert("x", ["https://a.example/", "https://x.example/"]),
                               y=vert("y", ["https://y.example/"]))
        with p1, p2:
            out = searchapis.top_up(self.base, "q", 3)
        self.assertEqual([r["url"] for r in out], ["https://a.example/", "https://x.example/", "https://y.example/"])
        self.assertEqual(calls, ["x", "y"])

    def test_full_list_calls_no_vertical(self):
        boom = mock.Mock(side_effect=AssertionError("must not be called"))
        p1, p2 = self._patched({}, x=boom)
        with p1, p2:
            self.assertEqual(searchapis.top_up(self.base, "q", 1), self.base)

    def test_empty_env_disables(self):
        boom = mock.Mock(side_effect=AssertionError)
        p1, p2 = self._patched({"DR_SEARCH_VERTICALS": ""}, x=boom)
        with p1, p2:
            self.assertEqual(searchapis.top_up(self.base, "q", 5), self.base)

    def test_chain_tops_up_after_general_results(self):
        with mock.patch.object(websearch, "brave_search", return_value=[]), \
                mock.patch.object(websearch, "bing_search", return_value=self.base), \
                mock.patch.object(searchapis, "top_up", side_effect=lambda r, *a, **k: r + ["V"]) as top:
            self.assertEqual(websearch.web_search_chain("q", 5), self.base + ["V"])
            top.assert_called_once()


if __name__ == "__main__":
    unittest.main()
