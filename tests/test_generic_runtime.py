"""GenericRuntime pieces that need no network: SearXNG parsing, URL gating, run_parallel contract."""

import json
import os
import subprocess
import unittest
from unittest import mock

from runtime.generic import GenericRuntime


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
        with mock.patch("requests.get") as get:
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
