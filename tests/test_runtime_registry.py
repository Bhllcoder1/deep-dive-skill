"""Runtime registry and platform detection."""

import os
import unittest
from unittest import mock

import harness
import runtime
from runtime.base import BaseRuntime

EXPECTED = {
    "hermes", "claude_code", "generic", "aider", "codex", "cline", "cursor", "gemini",
    "copilot", "amazon_q", "windsurf", "kimi", "glm", "minimax", "antigravity",
}


class RegistryTests(unittest.TestCase):
    def test_all_builtin_runtimes_are_registered_and_resolve(self):
        for name in sorted(EXPECTED):
            with self.subTest(name=name):
                rt = runtime.get_runtime(name)
                self.assertIsInstance(rt, BaseRuntime)
                self.assertTrue(rt.name)

    def test_registry_is_populated_with_real_targets(self):
        self.assertTrue(EXPECTED <= set(runtime.registered_names()))
        for name in EXPECTED:
            self.assertIsNotNone(runtime._RUNTIME_REGISTRY[name], name)

    def test_register_is_honoured_by_get_runtime(self):
        class Custom(runtime.base.BaseRuntime):
            name = "custom"
            def setup(self): return True
            def agent_call(self, prompt, schema=None, label="", phase=""): return None
            def web_search(self, query, max_results=6): return []
            def web_fetch(self, url): return None
            def run_parallel(self, fn_list, max_workers=3): return []

        runtime.register("custom_test_rt", Custom)
        try:
            self.assertIsInstance(runtime.get_runtime("custom_test_rt"), Custom)
            self.assertIn("custom_test_rt", runtime.registered_names())
        finally:
            runtime._RUNTIME_REGISTRY.pop("custom_test_rt", None)

    def test_unknown_runtime_falls_back_to_generic(self):
        self.assertEqual(runtime.get_runtime("does-not-exist").name, "generic")

    def test_harness_accepts_exactly_the_registered_runtimes(self):
        self.assertEqual(harness._runtime_names(), set(runtime.registered_names()) | {"auto"})


class DetectTests(unittest.TestCase):
    ENV_FLAGS = {
        "HERMES_AGENT": "hermes", "AIDER_VERSION": "aider", "CODEX_CLI": "codex",
        "CLINE_MCP": "cline", "CURSOR_CLI": "cursor", "GEMINI_CLI": "gemini",
        "COPILOT_CLI": "copilot", "AMAZON_Q_CLI": "amazon_q", "WINDSURF_CLI": "windsurf",
        "KIMI_CLI": "kimi", "GLM_CLI": "glm", "MINIMAX_CLI": "minimax",
        "ANTIGRAVITY_CLI": "antigravity",
    }

    def test_each_env_flag_selects_its_runtime(self):
        for flag, expected in self.ENV_FLAGS.items():
            with self.subTest(flag=flag), mock.patch.dict(os.environ, {flag: "x"}, clear=True):
                self.assertEqual(runtime.detect(), expected)

    def test_claude_code_flag(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=True):
            self.assertEqual(runtime.detect(), "claude_code")

    def test_default_is_generic_and_force_wins(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runtime.detect(), "generic")
        with mock.patch.dict(os.environ, {"DR_RUNTIME": "kimi", "CODEX_CLI": "x"}, clear=True):
            self.assertEqual(runtime.detect(), "kimi")


if __name__ == "__main__":
    unittest.main()


class UnknownRuntimeWarningTests(unittest.TestCase):
    def test_unknown_runtime_is_logged(self):
        with self.assertLogs("deepdive.runtime", level="WARNING") as captured:
            runtime.get_runtime("typo-runtime")
        self.assertIn("typo-runtime", captured.output[0])
