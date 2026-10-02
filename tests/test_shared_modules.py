"""Shared building blocks: URL safety, JSON extraction, bounded parallelism, safe fetch."""

import subprocess
import time
import unittest

from core.jsonparse import extract_json_object
from core.parallel import run_bounded
from core.safefetch import fetch_text_with_curl, html_to_text
from core.urlsafe import (host_resolves_public, is_public_ip, is_safe_to_connect,
                          normalize_public_url, resolve_public)


def resolver_for(*addresses):
    return lambda host, port=None, type=None: [(0, 0, 0, "", (a, 0)) for a in addresses]


class UrlSafetyTests(unittest.TestCase):
    def test_rejects_unsafe_urls(self):
        for url in [
            "http://localhost/", "http://foo.localhost/", "http://127.0.0.1/", "http://10.1.2.3/",
            "http://172.16.0.1/", "http://192.168.0.1/", "http://169.254.169.254/", "http://100.64.0.1/",
            "http://[::1]/", "http://[::ffff:127.0.0.1]/", "http://[fe80::1]/", "http://0.0.0.0/",
            "http://2130706433/", "http://0x7f.0.0.1/", "http://017700000001/", "http://printer.local/",
            "http://db.internal/", "file:///etc/passwd", "ftp://example.com/", "gopher://example.com/",
            "http://user:pw@example.com/", "http://example.com:badport/", "http:///nohost",
            "javascript:alert(1)", "", "  ", None, 5, "http://exa mple.com/", "https://e.com/" + "a" * 3000,
        ]:
            with self.subTest(url=url):
                self.assertIsNone(normalize_public_url(url))

    def test_accepts_and_normalizes_public_urls(self):
        self.assertEqual(normalize_public_url("  HTTPS://Example.COM./Path?q=1#frag "), "https://example.com/Path?q=1")
        self.assertEqual(normalize_public_url("http://example.com"), "http://example.com/")
        self.assertEqual(normalize_public_url("http://8.8.8.8:8080/x"), "http://8.8.8.8:8080/x")

    def test_public_ip_classification(self):
        self.assertTrue(is_public_ip("93.184.216.34"))
        self.assertTrue(is_public_ip("2606:2800:220:1:248:1893:25c8:1946"))
        for bad in ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:10.0.0.1", "garbage"]:
            self.assertFalse(is_public_ip(bad), bad)


class DnsRebindingTests(unittest.TestCase):
    def test_public_name_resolving_to_private_ip_is_rejected(self):
        self.assertFalse(host_resolves_public("evil.example", resolver_for("10.0.0.7")))

    def test_any_private_answer_rejects(self):
        self.assertIsNone(resolve_public("evil.example", resolver_for("93.184.216.34", "127.0.0.1")))

    def test_public_resolution_passes_and_failure_rejects(self):
        self.assertEqual(resolve_public("ok.example", resolver_for("93.184.216.34")), ["93.184.216.34"])

        def boom(*args, **kwargs):
            raise OSError("nxdomain")
        self.assertIsNone(resolve_public("nx.example", boom))

    def test_is_safe_to_connect_combines_both_checks(self):
        self.assertTrue(is_safe_to_connect("https://ok.example/a", resolver_for("93.184.216.34")))
        self.assertFalse(is_safe_to_connect("https://ok.example/a", resolver_for("192.168.1.5")))
        self.assertFalse(is_safe_to_connect("http://localhost/", resolver_for("93.184.216.34")))


class _Proc:
    def __init__(self, out, code=0):
        self.stdout, self.returncode = out, code


class SafeFetchTests(unittest.TestCase):
    PUBLIC = staticmethod(resolver_for("93.184.216.34"))

    def test_connection_is_pinned_to_the_checked_address(self):
        seen = []

        def runner(cmd, **kwargs):
            seen.append(cmd)
            return _Proc("<p>hello</p>\n200\t")
        text = fetch_text_with_curl("https://ok.example/a", resolver=self.PUBLIC, runner=runner)
        self.assertEqual(text, "hello")
        self.assertIn("ok.example:443:93.184.216.34", seen[0])
        self.assertIn("--max-redirs", seen[0])

    def test_redirect_to_private_host_is_blocked(self):
        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            return _Proc("\n302\thttp://169.254.169.254/latest/meta-data")
        self.assertIsNone(fetch_text_with_curl("https://ok.example/a", resolver=self.PUBLIC, runner=runner))
        self.assertEqual(len(calls), 1)

    def test_redirect_to_name_resolving_privately_is_blocked(self):
        def resolver(host, port=None, type=None):
            return resolver_for("10.0.0.9" if host == "inner.example" else "93.184.216.34")(host)

        def runner(cmd, **kwargs):
            return _Proc("\n301\thttps://inner.example/x")
        self.assertIsNone(fetch_text_with_curl("https://ok.example/a", resolver=resolver, runner=runner))

    def test_public_redirect_is_followed_and_loops_are_bounded(self):
        seq = [_Proc("\n302\thttps://ok.example/b"), _Proc("done\n200\t")]
        self.assertEqual(fetch_text_with_curl("https://ok.example/a", resolver=self.PUBLIC,
                                              runner=lambda *a, **k: seq.pop(0)), "done")
        loop = lambda *a, **k: _Proc("\n302\thttps://ok.example/a")
        self.assertIsNone(fetch_text_with_curl("https://ok.example/a", resolver=self.PUBLIC, runner=loop))

    def test_http_errors_and_curl_failures_return_none(self):
        self.assertIsNone(fetch_text_with_curl("https://ok.example/", resolver=self.PUBLIC,
                                               runner=lambda *a, **k: _Proc("x\n404\t")))

        def broken(*a, **k):
            raise subprocess.TimeoutExpired("curl", 1)
        self.assertIsNone(fetch_text_with_curl("https://ok.example/", resolver=self.PUBLIC, runner=broken))

    def test_html_to_text_strips_scripts(self):
        self.assertEqual(html_to_text("<script>x()</script><p>a &amp; b</p><!-- c -->"), "a & b")


class JsonParseTests(unittest.TestCase):
    def test_extraction_variants(self):
        cases = {
            '{"a": 1}': {"a": 1},
            '```json\n{"a": 1}\n```': {"a": 1},
            'Here you go: {"a": {"b": 2}} thanks': {"a": {"b": 2}},
            '﻿{"a": 1}': {"a": 1},
            'noise {broken {"a": 3} tail': {"a": 3},
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_json_object(text), expected)

    def test_rejects_non_objects_and_truncated(self):
        for text in ['[1, 2]', '"s"', '42', '{"a": ', '', '   ', None, 5, 'no json']:
            with self.subTest(text=text):
                self.assertIsNone(extract_json_object(text))

    def test_required_keys_skip_non_matching_objects(self):
        schema = {"required": ["results"]}
        self.assertEqual(extract_json_object('{"x": 1} then {"results": []}', schema), {"results": []})
        self.assertIsNone(extract_json_object('{"x": 1}', schema))

    def test_dict_passthrough(self):
        self.assertEqual(extract_json_object({"a": 1}), {"a": 1})


class RunBoundedTests(unittest.TestCase):
    def test_order_and_error_isolation(self):
        errors = []
        out = run_bounded([lambda: 1, lambda: 1 / 0, lambda: 3], 2, on_error=lambda i, e: errors.append(i))
        self.assertEqual(out, [1, None, 3])
        self.assertEqual(errors, [1])

    def test_worker_bound_is_respected(self):
        import threading
        active, peak, lock = [0], [0], threading.Lock()

        def task():
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with lock:
                active[0] -= 1
        run_bounded([task] * 12, 3)
        self.assertLessEqual(peak[0], 3)

    def test_timeout_returns_partial_results(self):
        timed_out = []
        start = time.monotonic()
        out = run_bounded([lambda: "fast", lambda: time.sleep(0.6) or "slow"], 2, timeout=0.1,
                          on_timeout=timed_out.append)
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertEqual(out, ["fast", None])
        self.assertEqual(timed_out, [1])

    def test_empty(self):
        self.assertEqual(run_bounded([], 3), [])


if __name__ == "__main__":
    unittest.main()
