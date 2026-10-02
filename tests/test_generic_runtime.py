"""GenericRuntime pieces that need no network: SearXNG parsing, URL gating, run_parallel contract."""

import json
import os
import subprocess
import unittest
from unittest import mock

from runtime.generic import GenericRuntime
from tests.fakes import fake_requests


class _Done:
    returncode = 0

    def __init__(self, payload):
        self.stdout = json.dumps(payload)


class SearxngTests(unittest.TestCase):
    def _runtime(self):
        rt = GenericRuntime()
        rt._has_requests, rt._curl_path = False, "curl"
        return rt

    def test_searxng_results_are_parsed_and_unsafe_urls_dropped(self):
        payload = {"results": [
            {"url": "https://a.example/x", "title": "A", "content": "snippet"},
            {"url": "http://127.0.0.1/admin", "title": "bad"},
            {"url": "https://a.example/x", "title": "dupe"},
            "garbage",
        ]}
        with mock.patch.dict(os.environ, {"SearXNG_URL": "http://localhost:8080"}), \
                mock.patch("runtime.generic.subprocess.run", return_value=_Done(payload)) as run:
            results = self._runtime().web_search("q")
        self.assertEqual([r["url"] for r in results], ["https://a.example/x"])
        self.assertIn("http://localhost:8080/search?", run.call_args[0][0][-1])

    def test_hermes_style_searxng_url_name_is_accepted(self):
        payload = {"results": [{"url": "https://a.example/x", "title": "A", "content": "c"}]}
        with mock.patch.dict(os.environ, {"SEARXNG_URL": "http://127.0.0.1:8888"}, clear=True), \
                mock.patch("runtime.generic.subprocess.run", return_value=_Done(payload)):
            self.assertEqual(len(self._runtime()._searxng_results("q", 5)), 1)

    def test_invalid_searxng_url_is_ignored(self):
        with mock.patch.dict(os.environ, {"SearXNG_URL": "javascript:alert(1)"}):
            self.assertEqual(self._runtime()._searxng_results("q", 5), [])

    def test_searxng_failure_is_empty(self):
        with mock.patch.dict(os.environ, {"SearXNG_URL": "http://localhost:8080"}), \
                mock.patch("runtime.generic.subprocess.run", side_effect=subprocess.TimeoutExpired("curl", 1)):
            self.assertEqual(self._runtime()._searxng_results("q", 5), [])


class WebFetchGuardTests(unittest.TestCase):
    def test_private_and_rebound_hosts_are_not_fetched(self):
        rt = GenericRuntime()
        rt._has_requests = True
        patcher, fake = fake_requests()
        get = fake.get
        with patcher:
            self.assertIsNone(rt.web_fetch("http://127.0.0.1/"))
            self.assertIsNone(rt.web_fetch("http://169.254.169.254/latest"))
            with mock.patch("core.urlsafe.socket.getaddrinfo", return_value=[(0, 0, 0, "", ("10.0.0.5", 0))]):
                self.assertIsNone(rt.web_fetch("https://rebind.example/"))
        get.assert_not_called()


class RunParallelContractTests(unittest.TestCase):
    def test_validation_and_order(self):
        rt = GenericRuntime()
        self.assertEqual(rt.run_parallel([lambda: 1, lambda: 2, lambda: 3], 2), [1, 2, 3])
        self.assertEqual(rt.run_parallel([], 2), [])
        with self.assertRaises(TypeError):
            rt.run_parallel("nope")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            rt.run_parallel([1])  # type: ignore[list-item]
        with self.assertRaises(ValueError):
            rt.run_parallel([lambda: 1], 0)

    def test_failed_task_becomes_none(self):
        rt = GenericRuntime()
        rt.log = mock.Mock()
        self.assertEqual(rt.run_parallel([lambda: 1 / 0, lambda: 2], 2), [None, 2])
        rt.log.assert_called()


if __name__ == "__main__":
    unittest.main()


SECRET = "sk-TESTSECRETVALUE123456"


def _ready_runtime(has_requests=False):
    rt = GenericRuntime()
    rt._ready, rt._api_key = True, SECRET
    rt._api_url = "https://api.example/v1/chat/completions"
    rt._has_requests, rt._curl_path = has_requests, "curl"
    return rt


class RetryTests(unittest.TestCase):
    def _run(self, outcomes):
        rt = _ready_runtime()
        calls = []

        def once(payload, schema):
            calls.append(1)
            return outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        with mock.patch.object(rt, "_post_once", side_effect=once), \
                mock.patch("runtime.generic.time.sleep") as sleep:
            result = rt.agent_call("prompt", schema={"type": "object"})
        return result, len(calls), sleep

    def test_transient_failures_are_retried_with_backoff_then_succeed(self):
        result, calls, sleep = self._run([(None, True), (None, True), ({"ok": 1}, False)])
        self.assertEqual((result, calls), ({"ok": 1}, 3))
        self.assertEqual(sleep.call_count, 2)
        first, second = (c.args[0] for c in sleep.call_args_list)
        self.assertTrue(0.5 <= first <= 1.0 and 1.0 <= second <= 2.0, (first, second))

    def test_permanent_failure_is_not_retried(self):
        result, calls, sleep = self._run([(None, False)])
        self.assertEqual((result, calls), (None, 1))
        sleep.assert_not_called()

    def test_retries_are_bounded(self):
        result, calls, _ = self._run([(None, True)])
        self.assertEqual((result, calls), (None, 3))

    def test_http_status_classification_with_requests(self):
        rt = _ready_runtime(has_requests=True)
        for status, expected in [(429, True), (503, True), (401, False), (400, False)]:
            response = mock.Mock(ok=False, status_code=status, text="err")
            patcher, fake = fake_requests()
            fake.post.return_value = response
            with self.subTest(status=status), patcher:
                self.assertEqual(rt._requests_call({}, None), (None, expected))

    def test_curl_path_is_used_only_without_requests(self):
        rt = _ready_runtime(has_requests=True)
        with mock.patch.object(rt, "_requests_call", return_value=(None, False)) as r, \
                mock.patch.object(rt, "_curl_call") as c:
            rt._post_once({}, None)
        r.assert_called_once()
        c.assert_not_called()


class SecretHandlingTests(unittest.TestCase):
    def test_api_key_never_appears_in_curl_argv(self):
        rt = _ready_runtime()
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            header_arg = cmd[cmd.index("-H") + 1]
            with open(header_arg[1:]) as handle:
                seen["header_file"] = handle.read()
            body = json.dumps({"choices": [{"message": {"content": '{"ok": 1}'}}]})
            return mock.Mock(returncode=0, stdout=body + "\n200", stderr="")
        with mock.patch("runtime.generic.subprocess.run", side_effect=fake_run):
            result, retryable = rt._curl_call({"m": 1}, None)
        self.assertEqual((result, retryable), ({"ok": 1}, False))
        self.assertFalse(any(SECRET in part for part in seen["cmd"]))
        self.assertIn(SECRET, seen["header_file"])

    def test_curl_status_429_is_retryable(self):
        rt = _ready_runtime()
        with mock.patch("runtime.generic.subprocess.run",
                        return_value=mock.Mock(returncode=0, stdout="busy\n429", stderr="")):
            self.assertEqual(rt._curl_call({}, None), (None, True))

    def test_header_file_is_private_and_removed(self):
        import stat
        from core.safefetch import secret_header_file
        with secret_header_file({"Authorization": "Bearer x"}) as path:
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertFalse(os.path.exists(path))


class ClaudeCodeFallbackEndpointTests(unittest.TestCase):
    def test_invalid_llm_api_base_is_rejected_before_any_request(self):
        from runtime.claude_code import ClaudeCodeRuntime
        rt = ClaudeCodeRuntime()
        rt._api_key = "sk-test-key-123456"
        rt.log = mock.Mock()
        patcher, fake = fake_requests()
        with mock.patch.dict(os.environ, {"LLM_API_BASE": "file:///etc/passwd"}), patcher:
            self.assertIsNone(rt._generic_agent_call("p", None))
        fake.post.assert_not_called()
        self.assertTrue(any("LLM_API_BASE" in call.args[0] for call in rt.log.call_args_list))
