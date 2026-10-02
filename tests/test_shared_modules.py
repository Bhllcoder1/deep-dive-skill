"""Shared building blocks: URL safety, JSON extraction, bounded parallelism, safe fetch."""

import os
import subprocess
import time
import unittest
from unittest import mock

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


class DdgParserTests(unittest.TestCase):
    PAGE = '''
    <div class="result"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.org%2Fpaper%3Fid%3D1&amp;rut=abc">Example <b>Paper</b></a>
      <a class="result__snippet" href="x">A short   snippet</a></div>
    <div class="result"><a class="result__a" href="https://other.example/page">Other</a></div>
    <div class="result"><a class="result__a" href="https://other.example/page">Duplicate</a></div>
    <div class="result"><a class="result__a" href="http://127.0.0.1/admin">Local</a></div>
    <div class="result"><a class="result__a" href="/relative">Relative</a></div>
    '''

    def test_parse(self):
        from core.websearch import parse_ddg_html
        results = parse_ddg_html(self.PAGE, 10)
        self.assertEqual([r["url"] for r in results],
                         ["https://www.example.org/paper?id=1", "https://other.example/page"])
        self.assertEqual(results[0]["title"], "Example Paper")
        self.assertEqual(results[0]["snippet"], "A short snippet")

    def test_limit_and_garbage(self):
        from core.websearch import parse_ddg_html, unwrap_ddg_url
        self.assertEqual(len(parse_ddg_html(self.PAGE, 1)), 1)
        self.assertEqual(parse_ddg_html("", 5), [])
        self.assertEqual(parse_ddg_html(None, 5), [])  # type: ignore[arg-type]
        self.assertEqual(unwrap_ddg_url("https://a.example/x"), "https://a.example/x")

    def setUp(self):
        from core import websearch
        websearch.reset_ddg_state()
        self.addCleanup(websearch.reset_ddg_state)

    def test_curl_search_uses_runner_and_handles_failure(self):
        from core.websearch import ddg_html_search_with_curl

        class Proc:
            returncode, stdout = 0, DdgParserTests.PAGE + "\n200"
        nosleep = lambda s: None
        self.assertEqual(len(ddg_html_search_with_curl("q", 5, runner=lambda *a, **k: Proc(), sleep=nosleep)), 2)
        Proc.returncode = 22
        self.assertEqual(ddg_html_search_with_curl("q", 5, runner=lambda *a, **k: Proc(), sleep=nosleep), [])

    def test_bot_challenge_trips_the_breaker_and_skips_later_calls(self):
        from core import websearch

        class Challenge:
            returncode, stdout = 0, '<div class="anomaly-modal">x</div>\n202'
        calls = []

        def runner(*a, **k):
            calls.append(1)
            return Challenge()
        nosleep = lambda s: None
        with self.assertLogs("deepdive.websearch", level="WARNING"):
            self.assertEqual(websearch.ddg_html_search_with_curl("q", 5, runner=runner, sleep=nosleep), [])
        self.assertTrue(websearch.ddg_blocked())
        self.assertEqual(websearch.ddg_html_search_with_curl("q", 5, runner=runner, sleep=nosleep), [])
        self.assertEqual(len(calls), 1, "the second call must not hit DuckDuckGo")

    def test_requests_are_spaced_out(self):
        from core.websearch import ddg_html_search_with_curl
        slept = []

        class Ok:
            returncode, stdout = 0, "\n200"
        for _ in range(2):
            ddg_html_search_with_curl("q", 5, runner=lambda *a, **k: Ok(), sleep=slept.append)
        self.assertEqual(len(slept), 1)
        self.assertGreater(slept[0], 0)


class SearchChainTests(unittest.TestCase):
    def setUp(self):
        from core import websearch
        patcher = mock.patch.dict(os.environ, {"DR_SEARCH_VERTICALS": ""})  # chain-order tests: no top-up
        patcher.start()
        self.addCleanup(patcher.stop)
        websearch.reset_ddg_state()
        self.addCleanup(websearch.reset_ddg_state)

    @staticmethod
    def _runner(routes):
        def run(cmd, **kwargs):
            url = cmd[-1]
            for needle, (code, out) in routes.items():
                if needle in url:
                    return type("P", (), {"returncode": code, "stdout": out})()
            return type("P", (), {"returncode": 22, "stdout": ""})()
        return run

    def test_wikipedia_is_the_keyless_last_resort(self):
        import json as _json
        from unittest import mock as _mock
        from core import websearch
        wiki = _json.dumps({"query": {"search": [{"title": "Rust (programming language)", "snippet": "a <b>language</b>"}]}})
        runner = self._runner({"duckduckgo": (0, '<x class="anomaly-modal">\n202'), "wikipedia.org": (0, wiki)})
        with _mock.patch.object(websearch.time, "sleep"), _mock.patch.dict("os.environ", {"DR_SEARCH_VERTICALS": ""}, clear=True):
            results = websearch.web_search_chain("rust", 3, runner=runner)
        self.assertEqual(results[0]["url"], "https://en.wikipedia.org/wiki/Rust_%28programming_language%29")
        self.assertEqual(results[0]["snippet"], "a language")

    def test_brave_is_first_when_keyed_and_key_stays_out_of_argv(self):
        import json as _json
        from unittest import mock as _mock
        from core import websearch
        seen = []
        payload = _json.dumps({"web": {"results": [{"url": "https://a.example/x", "title": "A", "description": "d"},
                                                   {"url": "http://127.0.0.1/", "title": "bad"}]}})

        def runner(cmd, **kwargs):
            seen.append(cmd)
            return type("P", (), {"returncode": 0, "stdout": payload})()
        with _mock.patch.dict("os.environ", {"BRAVE_API_KEY": "brave-secret-key-123", "DR_SEARCH_VERTICALS": ""}, clear=True):
            results = websearch.web_search_chain("q", 5, runner=runner)
        self.assertEqual([r["url"] for r in results], ["https://a.example/x"])
        self.assertEqual(len(seen), 1)
        self.assertFalse(any("brave-secret-key-123" in part for part in seen[0]))

    def test_everything_down_returns_empty(self):
        from unittest import mock as _mock
        from core import websearch
        with _mock.patch.object(websearch.time, "sleep"), _mock.patch.dict("os.environ", {"DR_SEARCH_VERTICALS": ""}, clear=True):
            self.assertEqual(websearch.web_search_chain("q", 3, runner=self._runner({})), [])


class BingAndChainOrderTests(unittest.TestCase):
    PAGE = ('<ol><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=x&amp;u=a1aHR0cHM6Ly9kb2MucnVzdC1sYW5nLm9yZy9ib29rL2NoMDQtMDAtdW5kZXJzdGFuZGluZy1vd25lcnNoaXAuaHRtbA&amp;ntb=1">Understanding <b>Ownership</b></a></h2>'
            '<div class="b_caption"><p>Ownership is Rust\'s most unique feature</p></div></li>'
            '<li class="b_algo"><h2><a href="https://example.org/direct">Direct</a></h2></li>'
            '<li class="b_algo"><h2><a href="http://127.0.0.1/x">Local</a></h2></li></ol>')

    def setUp(self):
        from core import websearch
        patcher = mock.patch.dict(os.environ, {"DR_SEARCH_VERTICALS": ""})  # chain-order tests: no top-up
        patcher.start()
        self.addCleanup(patcher.stop)
        websearch.reset_ddg_state()
        self.addCleanup(websearch.reset_ddg_state)

    def test_bing_redirect_links_are_decoded_and_unsafe_dropped(self):
        from core.websearch import parse_bing_html
        results = parse_bing_html(self.PAGE, 10)
        self.assertEqual([r["url"] for r in results],
                         ["https://doc.rust-lang.org/book/ch04-00-understanding-ownership.html", "https://example.org/direct"])
        self.assertEqual(results[0]["title"], "Understanding Ownership")
        self.assertIn("unique feature", results[0]["snippet"])

    def test_chain_uses_bing_and_never_touches_duckduckgo_by_default(self):
        from unittest import mock as _mock
        from core import websearch
        urls = []

        def runner(cmd, **kwargs):
            urls.append(cmd[-1])
            return type("P", (), {"returncode": 0, "stdout": BingAndChainOrderTests.PAGE})()
        with _mock.patch.dict("os.environ", {"DR_SEARCH_VERTICALS": ""}, clear=True):
            results = websearch.web_search_chain("q", 5, runner=runner)
        self.assertEqual(len(results), 2)
        self.assertTrue(all("duckduckgo" not in u for u in urls), urls)

    def test_duckduckgo_is_opt_in_last_resort(self):
        from unittest import mock as _mock
        from core import websearch
        urls = []

        def runner(cmd, **kwargs):
            urls.append(cmd[-1])
            return type("P", (), {"returncode": 22, "stdout": ""})()
        with _mock.patch.dict("os.environ", {"DR_SEARCH_DDG": "1", "DR_SEARCH_VERTICALS": ""}, clear=True), \
                _mock.patch.object(websearch.time, "sleep"):
            websearch.web_search_chain("q", 5, runner=runner)
        self.assertTrue(any("duckduckgo" in u for u in urls))
        self.assertIn("duckduckgo", urls[-1])


class ProxyTests(unittest.TestCase):
    def test_proxy_arg_validation(self):
        from core import websearch
        for value, expected in [("socks5h://127.0.0.1:9050", ["--proxy", "socks5h://127.0.0.1:9050"]),
                                ("", []), ("file:///etc/passwd", []), ("socks5h://x; rm -rf /", [])]:
            with mock.patch.dict(os.environ, {"DR_SEARCH_PROXY": value}):
                self.assertEqual(websearch._proxy_args(), expected)

    def test_proxy_puts_ddg_first_and_is_passed_to_curl(self):
        from core import websearch
        seen = []

        def run(cmd, **kwargs):
            seen.append(cmd)
            page = '<a class="result__a" href="https://example.org/x">T</a>'
            return subprocess.CompletedProcess(cmd, 0, stdout=page + "\n200", stderr="")
        websearch.reset_ddg_state()
        with mock.patch.dict(os.environ, {"DR_SEARCH_PROXY": "socks5h://127.0.0.1:9050", "DR_SEARCH_VERTICALS": ""}, clear=True), \
                mock.patch.object(websearch.time, "sleep"):
            out = websearch.web_search_chain("q", 3, runner=run)
        websearch.reset_ddg_state()
        self.assertEqual(out[0]["url"], "https://example.org/x")
        self.assertEqual(len(seen), 1)
        self.assertIn("duckduckgo", seen[0][-1])
        self.assertIn("--proxy", seen[0])


class KeyedBackendTests(unittest.TestCase):
    def _run(self, payload):
        calls = []

        def run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return subprocess.CompletedProcess(cmd, 0, stdout=__import__("json").dumps(payload), stderr="")
        return run, calls

    def test_tavily_and_serper_parse_and_keep_keys_out_of_argv(self):
        from core import websearch
        run, calls = self._run({"results": [{"url": "https://t.example/a", "title": "T", "content": "c"}]})
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-secret-123"}):
            out = websearch.tavily_search("q", 3, runner=run)
        self.assertEqual(out[0]["url"], "https://t.example/a")
        self.assertNotIn("tvly-secret-123", " ".join(calls[0][0]))
        self.assertIn('"query": "q"', calls[0][1]["input"])
        run, calls = self._run({"organic": [{"link": "https://s.example/b", "title": "S", "snippet": "x"}]})
        with mock.patch.dict(os.environ, {"SERPER_API_KEY": "serper-secret-123"}):
            self.assertEqual(websearch.serper_search("q", 3, runner=run)[0]["url"], "https://s.example/b")
        self.assertNotIn("serper-secret-123", " ".join(calls[0][0]))

    def test_unkeyed_backends_make_no_request(self):
        from core import websearch
        boom = mock.Mock(side_effect=AssertionError("no request without a key"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(websearch.tavily_search("q", 3, runner=boom), [])
            self.assertEqual(websearch.serper_search("q", 3, runner=boom), [])

    def test_jina_fetch_refuses_private_urls_and_is_opt_in_text(self):
        from core.safefetch import jina_reader_fetch
        boom = mock.Mock(side_effect=AssertionError("must not call"))
        self.assertIsNone(jina_reader_fetch("http://127.0.0.1/x", runner=boom))
        self.assertIsNone(jina_reader_fetch("file:///etc/passwd", runner=boom))
