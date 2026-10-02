"""CliRuntime: command resolution, shell-free execution, JSON parsing, generic fallback."""

import os
import stat
import tempfile
import unittest
from unittest import mock

from runtime import registered_names
from runtime.cli import AmazonQRuntime, CliRuntime, CodexRuntime, CopilotRuntime, GLMRuntime, KimiRuntime
from runtime.generic import GenericRuntime

CLI_NAMES = {"codex", "cursor", "gemini", "copilot", "amazon_q", "windsurf", "kimi", "glm", "minimax", "antigravity"}


def make_script(directory, name, body):
    path = os.path.join(directory, name)
    with open(path, "w") as handle:
        handle.write("#!/bin/sh\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


class CliRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def env(self, **extra):
        return mock.patch.dict(os.environ, {"PATH": self.dir, "HOME": self.dir, **extra}, clear=True)

    def test_every_cli_adapter_is_a_cli_runtime(self):
        import runtime
        for name in CLI_NAMES:
            with self.subTest(name=name):
                rt = runtime.get_runtime(name)
                self.assertIsInstance(rt, CliRuntime)
                self.assertEqual(rt.name, name)
        self.assertTrue(CLI_NAMES <= set(registered_names()))

    def test_default_binary_is_found_on_path(self):
        make_script(self.dir, "codex", "echo '{\"ok\": 1}'\n")
        with self.env():
            self.assertEqual(CodexRuntime()._cli_cmd, [os.path.join(self.dir, "codex")])

    def test_binary_aliases_and_subcommands(self):
        make_script(self.dir, "gh", "true\n")
        make_script(self.dir, "zai", "true\n")
        with self.env():
            self.assertEqual(CopilotRuntime()._cli_cmd, [os.path.join(self.dir, "gh"), "copilot"])
            self.assertEqual(GLMRuntime()._cli_cmd, [os.path.join(self.dir, "zai")])
            self.assertIsNone(AmazonQRuntime()._cli_cmd)

    def test_kimi_extra_install_path(self):
        os.makedirs(os.path.join(self.dir, ".kimi-code", "bin"))
        make_script(os.path.join(self.dir, ".kimi-code", "bin"), "kimi", "true\n")
        with self.env():
            self.assertEqual(KimiRuntime()._cli_cmd, [os.path.join(self.dir, ".kimi-code", "bin", "kimi")])

    def test_detection_flag_value_is_not_treated_as_a_command(self):
        make_script(self.dir, "codex", "true\n")
        with self.env(CODEX_CLI="1"):
            rt = CodexRuntime()
            self.assertEqual(rt._cli_cmd, [os.path.join(self.dir, "codex")])
            self.assertEqual(rt._override_ignored, "1")

    def test_override_runs_without_a_shell(self):
        marker = os.path.join(self.dir, "PWNED")
        script = make_script(self.dir, "mycli", 'cat >/dev/null; printf \'{"args": "%s"}\' "$*"\n')
        with self.env(CODEX_CLI=f"{script} --json ; touch {marker}"):
            rt = CodexRuntime()
            out = rt.agent_call("hello", schema={"required": ["args"]})
        self.assertFalse(os.path.exists(marker), "shell metacharacters must not be interpreted")
        self.assertEqual(out["args"], "--json ; touch " + marker)

    def test_shell_injection_in_override_is_ignored(self):
        marker = os.path.join(self.dir, "PWNED")
        with self.env(CODEX_CLI=f"true; touch {marker}"):
            self.assertIsNone(CodexRuntime()._cli_cmd)
        self.assertFalse(os.path.exists(marker))

    def test_cli_json_is_returned_without_touching_generic(self):
        make_script(self.dir, "codex", "cat >/dev/null; echo 'sure: {\"results\": []}'\n")
        with self.env(), mock.patch.object(GenericRuntime, "agent_call") as generic:
            self.assertEqual(CodexRuntime().agent_call("p"), {"results": []})
        generic.assert_not_called()

    def test_failures_fall_back_to_generic(self):
        cases = {"exit-code": "exit 3\n", "no-json": "echo hello\n"}
        for label, body in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                make_script(tmp, "codex", body)
                with mock.patch.dict(os.environ, {"PATH": tmp, "HOME": tmp}, clear=True), \
                        mock.patch.object(GenericRuntime, "agent_call", return_value={"from": "generic"}):
                    self.assertEqual(CodexRuntime().agent_call("p"), {"from": "generic"})

    def test_cli_runtime_does_not_need_an_api_key_to_be_ready(self):
        make_script(self.dir, "codex", "true\n")
        with self.env():
            rt = CodexRuntime()
            self.assertTrue(rt.setup())

    def test_without_cli_or_key_setup_fails(self):
        with self.env():
            self.assertFalse(CodexRuntime().setup())


if __name__ == "__main__":
    unittest.main()


class CliFallbackConfigTests(unittest.TestCase):
    def test_cli_runtime_loads_api_config_for_its_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_script(tmp, "codex", "exit 3\n")
            env = {"PATH": tmp, "HOME": tmp, "DEEPSEEK_API_KEY": "sk-fallback-key-123456"}
            with mock.patch.dict(os.environ, env, clear=True):
                rt = CodexRuntime()
                rt.setup()
                self.assertEqual(rt._api_key, "sk-fallback-key-123456")
                self.assertTrue(rt._api_url.endswith("/chat/completions"))

    def test_failing_cli_without_api_config_fails_fast_without_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_script(tmp, "codex", "exit 3\n")
            with mock.patch.dict(os.environ, {"PATH": tmp, "HOME": tmp}, clear=True), \
                    mock.patch("runtime.generic.time.sleep") as sleep, \
                    mock.patch.object(GenericRuntime, "_post_once") as post:
                self.assertIsNone(CodexRuntime().agent_call("p"))
        post.assert_not_called()
        sleep.assert_not_called()

    def test_plain_http_api_base_warns_unless_loopback(self):
        rt = GenericRuntime()
        with mock.patch.dict(os.environ, {"LLM_API_BASE": "http://llm.example/v1", "DEEPSEEK_API_KEY": "k"}):
            with self.assertLogs("deepdive.runtime.generic", level="WARNING"):
                rt._load_api_config()
        with mock.patch.dict(os.environ, {"LLM_API_BASE": "http://localhost:8000/v1", "DEEPSEEK_API_KEY": "k"}):
            with self.assertNoLogs("deepdive.runtime.generic", level="WARNING") if hasattr(self, "assertNoLogs") else mock.MagicMock():
                rt._load_api_config()
