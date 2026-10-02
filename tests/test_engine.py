"""Engine behaviour: search, URL safety, voting, synthesis, salvage, call accounting."""

import unittest

from tests.fakes import (FakeRuntime, claim_dict, run_engine, search_result,
                         simple_runtime, verdict)

U1 = "https://one.example/a"
U2 = "https://two.example/b"


class SearchPhaseTests(unittest.TestCase):
    def test_real_web_search_is_called_for_every_angle(self):
        rt = simple_runtime({U1: ["c1"]})
        run_engine(rt)
        self.assertEqual(rt.search_calls, ["query a", "query b"])

    def test_llm_is_not_asked_for_urls_when_search_returns_results(self):
        rt = simple_runtime({U1: ["c1"]})
        run_engine(rt)
        # angle A had real results; angle B was empty and may use the fallback,
        # but angle A must never reach the LLM search agent.
        searched = [label for phase, label in rt.agent_calls if phase == "Search"]
        self.assertNotIn("search:A", searched)

    def test_llm_search_is_fallback_when_search_is_empty_and_is_logged(self):
        rt = simple_runtime({U1: ["c1"]}, llm_search={"query b": [search_result(U2)]})
        rt.pages[U2] = "page two"
        rt.extractions[U2] = {"claims": [claim_dict("c2")], "sourceQuality": "primary"}
        result = run_engine(rt)
        self.assertIn("search:B", [label for phase, label in rt.agent_calls if phase == "Search"])
        self.assertTrue(any("fallback" in m.lower() for m in rt.logs), rt.logs)
        self.assertIn(U2, [s["url"] for s in result["sources"]])

    def test_search_backend_exception_falls_back_to_llm(self):
        rt = simple_runtime({U1: ["c1"]}, search_raises=True, llm_search={"query a": [search_result(U1)]})
        result = run_engine(rt)
        self.assertEqual(len(rt.search_calls), 2)
        self.assertEqual(rt.count("Search"), 2)
        self.assertIn(U1, [s["url"] for s in result["sources"]])

    def test_duplicate_urls_across_angles_are_fetched_once(self):
        rt = simple_runtime({U1: ["c1"]})
        rt.search["query b"] = [search_result(U1 + "#frag")]
        run_engine(rt)
        self.assertEqual(rt.fetch_calls.count(U1), 1)


class UrlSafetyTests(unittest.TestCase):
    UNSAFE = [
        "http://localhost/admin", "http://127.0.0.1/x", "http://10.0.0.5/x",
        "http://192.168.1.1/x", "http://169.254.169.254/latest/meta-data",
        "http://[::1]/x", "http://0.0.0.0/x", "file:///etc/passwd",
        "ftp://example.com/x", "http://user:pw@example.com/x", "javascript:alert(1)",
    ]

    def test_private_and_nonhttp_urls_are_never_fetched(self):
        results = [search_result(u) for u in self.UNSAFE] + [search_result(U1)]
        rt = FakeRuntime(search={"query a": results},
                         pages={U1: "ok"},
                         extractions={U1: {"claims": [claim_dict("c1")], "sourceQuality": "primary"}})
        run_engine(rt)
        self.assertEqual(rt.fetch_calls, [U1])


class VotingTests(unittest.TestCase):
    def _run(self, votes, **cfg):
        rt = simple_runtime({U1: ["the claim"]}, verdicts={"the claim": votes})
        return run_engine(rt, **cfg), rt

    def test_majority_refuted_is_killed(self):
        result, _ = self._run([verdict(True), verdict(True), verdict(False)])
        self.assertEqual([c["claim"] for c in result["refuted"]], ["the claim"])
        self.assertEqual(result["findings"], [])

    def test_tie_is_unverified_not_confirmed(self):
        result, _ = self._run([verdict(True), verdict(False)], VOTES_PER_CLAIM=2, REFUTATIONS_REQUIRED=2)
        self.assertEqual([c["claim"] for c in result["unverified"]], ["the claim"])
        self.assertEqual(result["refuted"], [])
        self.assertEqual(result["stats"]["confirmed"], 0)

    def test_malformed_verdict_counts_as_errored(self):
        result, _ = self._run([verdict(False), {"refuted": "yes"}, None])
        self.assertEqual(result["unverified"][0]["erroredVotes"], 2)
        self.assertEqual(result["stats"]["confirmed"], 0)

    def test_unanimous_support_is_confirmed(self):
        result, _ = self._run([verdict(False)] * 3)
        self.assertEqual(result["stats"]["confirmed"], 1)


class SynthesisTests(unittest.TestCase):
    def _runtime(self, synthesis):
        rt = simple_runtime(
            {U1: ["good claim"], U2: ["bad claim"]},
            verdicts={"bad claim": [verdict(True)] * 3},
            synthesis=synthesis,
        )
        return rt

    def test_only_confirmed_sources_are_cited(self):
        rt = self._runtime({
            "summary": "sum",
            "findings": [
                {"claim": "f1", "confidence": "high", "sources": [U1, U2, "https://made.up/x"], "evidence": "e", "vote": "3-0"},
                {"claim": "f2", "confidence": "low", "sources": [U2], "evidence": "e", "vote": "0-3"},
            ],
        })
        result = run_engine(rt)
        self.assertEqual([f["claim"] for f in result["findings"]], ["f1"])
        self.assertEqual(result["findings"][0]["sources"], [U1])

    def test_salvage_when_synthesis_fails(self):
        rt = self._runtime(None)
        result = run_engine(rt)
        self.assertEqual(result["findings"], [])
        self.assertEqual([c["source"] for c in result["confirmed"]], [U1])
        self.assertIn("Synthesis failed", result["summary"])

    def test_salvage_when_synthesis_cites_nothing_valid(self):
        rt = self._runtime({"summary": "s", "findings": [{"claim": "x", "sources": ["https://made.up/x"]}]})
        result = run_engine(rt)
        self.assertIn("confirmed", result)
        self.assertEqual(result["findings"], [])


class AgentCallAccountingTests(unittest.TestCase):
    def test_agent_calls_equals_real_calls_with_search_fallback_and_failed_fetch(self):
        rt = simple_runtime({U1: ["c1"], U2: ["c2"]}, llm_search={"query b": []})
        del rt.pages[U2]  # fetch failure => no extraction call for U2
        result = run_engine(rt)
        self.assertEqual(result["stats"]["agentCalls"], len(rt.agent_calls))

    def test_agent_calls_when_nothing_confirmed(self):
        rt = simple_runtime({U1: ["c1"]}, verdicts={"c1": [verdict(True)] * 3})
        result = run_engine(rt)
        self.assertEqual(result["stats"]["agentCalls"], len(rt.agent_calls))

    def test_agent_calls_in_salvage_path(self):
        rt = simple_runtime({U1: ["c1"]}, synthesis=None)
        result = run_engine(rt)
        self.assertEqual(result["stats"]["agentCalls"], len(rt.agent_calls))

    def test_agent_calls_in_normal_path(self):
        rt = simple_runtime({U1: ["c1"]}, synthesis={
            "summary": "s", "findings": [{"claim": "f", "sources": [U1], "confidence": "high"}]})
        result = run_engine(rt)
        self.assertEqual(result["stats"]["agentCalls"], len(rt.agent_calls))


class InputTests(unittest.TestCase):
    def test_empty_question(self):
        self.assertIn("error", run_engine(FakeRuntime(), question="   "))


if __name__ == "__main__":
    unittest.main()
