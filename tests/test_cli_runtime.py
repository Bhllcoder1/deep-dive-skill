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

    def test_default_binary_is_found_with_its_headless_flags(self):
        make_script(self.dir, "codex", "echo '{\"ok\": 1}'\n")
        with self.env():
            cmd = CodexRuntime()._cli_cmd
        self.assertEqual(cmd[:3], [os.path.join(self.dir, "codex"), "exec", "-"])
        self.assertIn("read-only", cmd)

    def test_copilot_probes_only_the_standalone_cli(self):
        make_script(self.dir, "gh", "true\n")
        with self.env():
            self.assertIsNone(CopilotRuntime()._cli_cmd)  # `gh copilot` is not a scriptable agent
        make_script(self.dir, "copilot", "true\n")
        with self.env():
            self.assertEqual(CopilotRuntime()._cli_cmd, [os.path.join(self.dir, "copilot"), "-p"])

    def test_platforms_without_a_known_headless_cli_are_never_probed(self):
        marker = os.path.join(self.dir, "LAUNCHED")
        for binary in ("windsurf", "antigravity", "glm", "zai", "minimax"):
            make_script(self.dir, binary, f"touch {marker}\n")
        from runtime.cli import AntigravityRuntime, MiniMaxRuntime, WindsurfRuntime
        with self.env():
            for cls in (WindsurfRuntime, AntigravityRuntime, GLMRuntime, MiniMaxRuntime):
                with self.subTest(cls=cls.__name__):
                    self.assertIsNone(cls()._cli_cmd)
        self.assertFalse(os.path.exists(marker), "an editor launcher must never be executed")

    def test_explicit_override_enables_a_platform_without_defaults(self):
        from runtime.cli import WindsurfRuntime
        script = make_script(self.dir, "mywind", "cat >/dev/null; echo '{\"ok\": 2}'\n")
        with self.env(WINDSURF_CLI=script):
            self.assertEqual(WindsurfRuntime().agent_call("p"), {"ok": 2})

    def test_amazon_q_and_cursor_use_arg_mode(self):
        from runtime.cli import CursorRuntime
        self.assertEqual((AmazonQRuntime.prompt_mode, CursorRuntime.prompt_mode, KimiRuntime.prompt_mode),
                         ("arg", "arg", "arg"))

    def test_kimi_extra_install_path(self):
        os.makedirs(os.path.join(self.dir, ".kimi-code", "bin"))
        make_script(os.path.join(self.dir, ".kimi-code", "bin"), "kimi", "true\n")
        with self.env():
            self.assertEqual(KimiRuntime()._cli_cmd, [os.path.join(self.dir, ".kimi-code", "bin", "kimi"), "-p"])

    def test_detection_flag_value_is_not_treated_as_a_command(self):
        make_script(self.dir, "codex", "true\n")
        with self.env(CODEX_CLI="1"):
            rt = CodexRuntime()
            self.assertEqual(rt._cli_cmd[0], os.path.join(self.dir, "codex"))
            self.assertEqual(rt._override_ignored, "1")

    def test_arg_mode_passes_prompt_as_last_argument_and_closes_stdin(self):
        make_script(self.dir, "kimi", 'printf \'{"last": "%s", "stdin": "%s"}\' "$(eval echo \\${$#})" "$(cat)"\n')
        with self.env():
            result = KimiRuntime().agent_call("hello-prompt")
        self.assertEqual(result, {"last": "hello-prompt", "stdin": ""})

    def test_cli_runs_in_an_empty_directory_not_the_users_project(self):
        make_script(self.dir, "codex", 'read x; n=0; for f in .[!.]* *; do [ -e "$f" ] && n=$((n+1)); done; printf \'{"cwd": "%s", "files": %s}\' "$PWD" "$n"\n')
        with self.env():
            result = CodexRuntime().agent_call("p")
        self.assertEqual(result["files"], 0)
        self.assertNotEqual(os.path.realpath(result["cwd"]), os.path.realpath(os.getcwd()))

    def test_failing_cli_is_skipped_after_repeated_failures(self):
        counter = os.path.join(self.dir, "count")
        make_script(self.dir, "codex", f"cat >/dev/null; echo x >> {counter}; exit 3\n")
        with self.env(), mock.patch.object(GenericRuntime, "agent_call", return_value={"api": 1}):
            rt = CodexRuntime()
            for _ in range(6):
                self.assertEqual(rt.agent_call("p"), {"api": 1})
        with open(counter) as handle:
            self.assertEqual(len(handle.readlines()), CodexRuntime.max_cli_failures)

    def test_binary_aliases_unused(self):
        make_script(self.dir, "q", "true\n")
        with self.env():
            self.assertEqual(AmazonQRuntime()._cli_cmd, [os.path.join(self.dir, "q"), "chat", "--no-interactive"])

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


class ClaudeCodeHeadlessTests(unittest.TestCase):
    def test_claude_p_is_the_real_response_channel(self):
        from runtime.claude_code import ClaudeCodeRuntime
        with tempfile.TemporaryDirectory() as tmp:
            make_script(tmp, "claude", 'cat >/dev/null; printf \'{"args": "%s"}\' "$*"\n')
            with mock.patch.dict(os.environ, {"PATH": tmp, "HOME": tmp}, clear=True):
                rt = ClaudeCodeRuntime()
                self.assertTrue(rt.setup())
                out = rt.agent_call("prompt", schema={"required": ["args"]})
        self.assertIn("-p", out["args"])
        self.assertIn("--no-session-persistence", out["args"])

    def test_opt_out_and_missing_cli_without_key(self):
        from runtime.claude_code import ClaudeCodeRuntime
        with tempfile.TemporaryDirectory() as tmp:
            make_script(tmp, "claude", "echo '{}'\n")
            with mock.patch.dict(os.environ, {"PATH": tmp, "HOME": tmp, "DR_CLAUDE_HEADLESS": "0"}, clear=True):
                self.assertFalse(ClaudeCodeRuntime().setup())  # no CLI use and no API key
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent", "HOME": "/nonexistent"}, clear=True):
            self.assertFalse(ClaudeCodeRuntime().setup())

    def test_api_key_alone_is_enough(self):
        from runtime.claude_code import ClaudeCodeRuntime
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent", "DEEPSEEK_API_KEY": "sk-abcdef123456"}, clear=True):
            self.assertTrue(ClaudeCodeRuntime().setup())


class HermesTests(unittest.TestCase):
    def test_hermes_z_is_used_without_any_api_key(self):
        from runtime.hermes import HermesRuntime
        with tempfile.TemporaryDirectory() as tmp:
            make_script(tmp, "hermes", 'printf \'{"flag": "%s", "prompt": "%s"}\' "$1" "$2"\n')
            make_script(tmp, "curl", "true\n")
            with mock.patch.dict(os.environ, {"PATH": tmp, "HOME": tmp}, clear=True):
                rt = HermesRuntime()
                self.assertTrue(rt.setup())
                self.assertEqual(rt.agent_call("hello"), {"flag": "-z", "prompt": "hello"})

    def test_key_is_read_from_hermes_env_file(self):
        from runtime.hermes import HermesRuntime
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".hermes"))
            with open(os.path.join(tmp, ".hermes", ".env"), "w") as handle:
                handle.write("DEEPSEEK_API_KEY=sk-from-hermes-env-123456\n")
            with mock.patch.dict(os.environ, {"PATH": "/nonexistent", "HOME": tmp}, clear=True):
                self.assertEqual(HermesRuntime()._find_api_key(), "sk-from-hermes-env-123456")

    def test_opt_out_without_key_is_not_ready(self):
        from runtime.hermes import HermesRuntime
        with tempfile.TemporaryDirectory() as tmp:
            make_script(tmp, "hermes", "true\n")
            make_script(tmp, "curl", "true\n")
            with mock.patch.dict(os.environ, {"PATH": tmp, "HOME": tmp, "DR_HERMES_CLI": "0"}, clear=True):
                self.assertFalse(HermesRuntime().setup())
