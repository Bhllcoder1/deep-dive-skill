"""Token/time efficiency and source diversity: early-stopped voting, excerpts, dedupe, cache, round-robin."""

import os
import tempfile
import unittest
from unittest import mock

from core import cache, textutil
from tests.fakes import FakeRuntime, claim_dict, run_engine, search_result, simple_runtime, verdict

U1, U2 = "https://one.example/a", "https://two.example/b"


class AdaptiveVotingTests(unittest.TestCase):
    def test_third_voter_only_runs_when_first_two_disagree(self):
        rt = simple_runtime({U1: ["agreed claim", "split claim"]},
                            verdicts={"split claim": [verdict(False), verdict(True), verdict(True)]})
        result = run_engine(rt)
        voters = [label.split(":", 1)[0] for phase, label in rt.agent_calls if phase == "Verify"]
        self.assertEqual(sorted(voters), ["v0", "v0", "v1", "v1", "v2"])  # v2 only for the split claim
        self.assertEqual(result["stats"]["confirmed"], 1)
        self.assertEqual([c["claim"] for c in result["refuted"]], ["split claim"])

    def test_outcomes_match_full_voting_for_all_vote_patterns(self):
        import itertools
        for pattern in itertools.product([True, False, None], repeat=3):
            votes = [verdict(p) if p is not None else None for p in pattern]
            result = run_engine(simple_runtime({U1: ["c"]}, verdicts={"c": votes}))
            refuted = sum(p is True for p in pattern)
            support = sum(p is False for p in pattern)
            expected = "refuted" if refuted >= 2 else ("confirmed" if support >= 2 else "unverified")
            actual = ("refuted" if result["refuted"] else "confirmed" if result["stats"]["confirmed"] else "unverified")
            self.assertEqual(actual, expected, pattern)

    def test_four_votes_two_required_keeps_full_voting(self):
        rt = simple_runtime({U1: ["c"]})
        run_engine(rt, votes_per_claim=4, refutations_required=2)
        self.assertEqual(rt.count("Verify"), 4)


class ExcerptTests(unittest.TestCase):
    def test_short_text_unchanged_and_long_text_keeps_relevant_paragraphs_in_order(self):
        self.assertEqual(textutil.excerpt("short", "q", 100), "short")
        filler = "\n\n".join(f"unrelated filler paragraph number {i} about nothing " * 5 for i in range(40))
        page = "Intro line\n\n" + filler + "\n\nBorrow checker lifetimes are verified at compile time.\n\n" + filler
        out = textutil.excerpt(page, "borrow checker lifetimes", 1500)
        self.assertLessEqual(len(out), 1500)
        self.assertIn("Borrow checker lifetimes", out)
        self.assertTrue(out.startswith("Intro line"))

    def test_context_around_and_similar(self):
        text = "alpha " * 100 + "The Quick  Brown fox." + " omega" * 100
        around = textutil.context_around(text, "the quick brown fox", 20)
        self.assertIn("Quick Brown fox", around)
        self.assertLess(len(around), 80)
        self.assertEqual(textutil.context_around(text, "absent phrase"), "")
        self.assertTrue(textutil.similar("Rust enforces ownership at compile time",
                                         "Rust enforces ownership at the compile time"))
        self.assertFalse(textutil.similar("Rust enforces ownership", "Python uses garbage collection"))

    def test_duplicate_claims_across_sources_are_merged_once(self):
        a = {"claim": "Rust enforces ownership at compile time", "sourceUrl": U1}
        b = {"claim": "Rust enforces ownership at the compile time", "sourceUrl": U2}
        out = textutil.dedupe_claims([a, b, {"claim": "Different thing entirely", "sourceUrl": U1}])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["alsoIn"], [U2])


class PipelineEfficiencyTests(unittest.TestCase):
    def test_verifier_prompt_gets_page_context_and_stats_report_tokens(self):
        rt = simple_runtime({U1: ["c1"]})
        rt.pages[U1] = "before text. quote for c1 and after text."
        result = run_engine(rt)
        verify_prompts = [p for phase, p in rt.prompts if phase == "Verify"]
        self.assertTrue(all("before text" in p for p in verify_prompts))
        self.assertGreater(result["stats"]["estTokens"]["in"], 0)

    def test_long_page_is_excerpted_but_quote_check_uses_full_page(self):
        rt = simple_runtime({U1: ["c1"]})
        rt.pages[U1] = ("filler words. " * 2000) + "quote for c1 appears late."
        result = run_engine(rt, excerpt_chars=1000)
        fetch_prompt = next(p for phase, p in rt.prompts if phase == "Fetch")
        self.assertLess(len(fetch_prompt), 3000)
        self.assertEqual(result["stats"]["claimsExtracted"], 1)

    def test_round_robin_and_domain_cap(self):
        a = [search_result(f"https://site.example/{i}") for i in range(4)] + [search_result("https://a.example/1")]
        b = [search_result("https://b.example/1"), search_result("https://b.example/2")]
        rt = FakeRuntime(search={"query a": a, "query b": b})
        run_engine(rt, max_fetch=4, max_per_domain=2)
        self.assertEqual(rt.fetch_calls, ["https://site.example/0", "https://b.example/1",
                                          "https://site.example/1", "https://b.example/2"])


class CacheTests(unittest.TestCase):
    def test_roundtrip_ttl_and_disable(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"DR_CACHE_DIR": tmp}), \
                mock.patch.object(cache, "_dir", lambda: tmp):
            self.assertIsNone(cache.get("fetch", "k"))
            cache.put("fetch", "k", "page")
            self.assertEqual(cache.get("fetch", "k"), "page")
            with mock.patch.dict(os.environ, {"DR_CACHE_TTL": "0"}):
                self.assertIsNone(cache.get("fetch", "k"))
            cache.put("fetch", "empty", None)  # failures are never cached
            self.assertIsNone(cache.get("fetch", "empty"))


if __name__ == "__main__":
    unittest.main()
