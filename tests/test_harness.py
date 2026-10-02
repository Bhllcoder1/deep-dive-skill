"""Harness: config validation, per-call env isolation, CLI flags, report printing, keyless error."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import harness
from tests.fakes import FakeRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DR_KEYS = list(harness._CONFIG_MAP.values())


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


class ConfigValidationTests(unittest.TestCase):
    def test_invalid_inputs_return_structured_errors(self):
        bad = [
            {"tier": "turbo"},
            {"angles": 0},
            {"angles": "many"},
            {"angles": True},
            {"votes_per_claim": 1, "refutations_required": 2},
            {"max_workers": 21},
            {"bogus_option": 1},
        ]
        for kwargs in bad:
            with self.subTest(kwargs=kwargs):
                result = quiet(harness.deep_research, "q", show_dashboard=False, **kwargs)
                self.assertIn("error", result)
                self.assertEqual(result["question"], "q")

    def test_bad_question_and_runtime(self):
        self.assertIn("error", harness.deep_research("  ", show_dashboard=False))
        self.assertIn("error", harness.deep_research(5, show_dashboard=False))
        self.assertIn("error", harness.deep_research("q", runtime_name="nope", show_dashboard=False))


class EnvIsolationTests(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in DR_KEYS}

    def tearDown(self):
        for key, value in self._saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def _research(self, rt, **kwargs):
        with mock.patch("runtime.get_runtime", return_value=rt):
            return quiet(harness.deep_research, "q", show_dashboard=False, **kwargs)

    def test_env_is_restored_after_call(self):
        rt = FakeRuntime()
        self._research(rt, angles=1, max_fetch=3)
        for key in DR_KEYS:
            self.assertNotIn(key, os.environ)

    def test_env_is_restored_even_when_runtime_raises(self):
        rt = FakeRuntime()
        rt.setup = mock.Mock(side_effect=RuntimeError("boom"))
        self._research(rt, angles=1)
        self.assertNotIn("DR_ANGLES", os.environ)

    def test_settings_do_not_leak_between_calls(self):
        angles = [{"label": f"L{i}", "query": f"query {i}", "rationale": "r"} for i in range(4)]
        first = self._research(FakeRuntime(angles=angles), angles=1)
        second = self._research(FakeRuntime(angles=angles), angles=3)
        third = self._research(FakeRuntime(angles=angles), angles=2)
        self.assertEqual([r["stats"]["angles"] for r in (first, second, third)], [1, 3, 2])

    def test_preexisting_env_is_preserved(self):
        os.environ["DR_ANGLES"] = "4"
        self._research(FakeRuntime(), angles=1)
        self.assertEqual(os.environ["DR_ANGLES"], "4")


class CliFlagTests(unittest.TestCase):
    def _main(self, argv):
        captured = {}

        def fake_deep_research(question, runtime_name=None, show_dashboard=True, **kwargs):
            captured.update(kwargs=kwargs, question=question)
            return {"question": question, "summary": "s", "findings": [], "stats": {}}

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(harness, "deep_research", fake_deep_research), \
                mock.patch.object(sys, "argv", ["harness.py"] + argv + ["-o", os.path.join(tmp, "o.json")]), \
                contextlib.redirect_stdout(io.StringIO()):
            code = harness.main()
        return code, captured

    def test_angles_and_refutations_flags_reach_the_api(self):
        code, captured = self._main(["q", "--angles", "3", "--refutations", "2", "--votes", "3"])
        self.assertEqual(code, 0)
        self.assertEqual(captured["kwargs"]["angles"], 3)
        self.assertEqual(captured["kwargs"]["refutations_required"], 2)
        self.assertEqual(captured["kwargs"]["votes_per_claim"], 3)


class PrintReportTests(unittest.TestCase):
    def _render(self, result):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            harness.print_report(result)
        return buf.getvalue()

    def test_unverified_claims_are_shown(self):
        out = self._render({"question": "q", "summary": "s", "findings": [],
                            "unverified": [{"claim": "maybe true claim", "erroredVotes": 1, "source": "https://x.example/"}]})
        self.assertIn("maybe true claim", out)

    def test_salvaged_confirmed_claims_are_shown(self):
        out = self._render({"question": "q", "summary": "Synthesis failed. 1 verified claims unmerged.", "findings": [],
                            "confirmed": [{"claim": "verified salvage claim", "source": "https://x.example/", "quote": "q", "vote": "3-0"}]})
        self.assertIn("verified salvage claim", out)

    def test_invalid_result_does_not_crash(self):
        self._render("nonsense")  # type: ignore[arg-type]


class KeylessRunTests(unittest.TestCase):
    def test_json_error_without_api_key(self):
        env = {k: v for k, v in os.environ.items()
               if k not in {"DEEPSEEK_API_KEY"} and not k.endswith("_CLI")
               and not k.startswith("CLAUDE") and k not in {"HERMES_AGENT", "AIDER_CHAT_MODE", "AIDER_VERSION", "CLINE_MCP", "DR_RUNTIME"}}
        with tempfile.TemporaryDirectory() as home:
            env["HOME"] = home  # no ~/.env fallback key
            env["DR_RUNTIME"] = "generic"  # never auto-detect a platform CLI during the test
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "harness.py"), "test", "--format", "json",
                 "-o", os.path.join(home, "out.json")],
                capture_output=True, text=True, env=env, cwd=home, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)  # stdout must be pure JSON
        self.assertIn("error", payload)
        self.assertEqual(payload["question"], "test")


if __name__ == "__main__":
    unittest.main()
