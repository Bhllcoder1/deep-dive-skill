"""Logging: redaction, stderr-only output, JSON lines with run id."""

import io
import json
import logging
import unittest
from unittest import mock

from core import logs
from core.config import Config
from tests.fakes import simple_runtime

U1 = "https://one.example/a"


class RedactionTests(unittest.TestCase):
    def test_secrets_are_masked(self):
        cases = [
            "Authorization: Bearer abcdef1234567890",
            "key sk-abcdefghijklmnop leaked",
            'api_key="supersecretvalue"',
            "GET /x?api_key=abc123456&q=1",
            "DEEPSEEK_API_KEY=sk-live-12345678",
        ]
        for text in cases:
            with self.subTest(text=text):
                out = logs.redact(text)
                for secret in ("abcdef1234567890", "abcdefghijklmnop", "supersecretvalue", "abc123456", "12345678"):
                    self.assertNotIn(secret, out)
                self.assertIn("[REDACTED]", out)

    def test_ordinary_text_is_untouched(self):
        self.assertEqual(logs.redact("Phase 3/5 — 4 kaynak"), "Phase 3/5 — 4 kaynak")


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger(logs.ROOT)
        self._saved = (list(self.logger.handlers), self.logger.level, self.logger.propagate)
        self.logger.handlers.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        self.logger.handlers[:] = self._saved[0]
        self.logger.setLevel(self._saved[1])
        self.logger.propagate = self._saved[2]

    def test_text_mode_writes_redacted_message_to_the_given_stream(self):
        stream = io.StringIO()
        logs.ensure_configured(stream)
        logs.get_logger("runtime").info("token=abcdefghijk done")
        self.assertEqual(stream.getvalue().strip(), "token=[REDACTED] done")

    def test_json_mode_includes_run_id(self):
        stream = io.StringIO()
        with mock.patch.dict("os.environ", {"DR_LOG_FORMAT": "json"}):
            logs.ensure_configured(stream)
        logs.get_logger("x").warning("hello", extra={"run_id": "abc12345"})
        record = json.loads(stream.getvalue())
        self.assertEqual((record["level"], record["run_id"], record["msg"]), ("WARNING", "abc12345", "hello"))

    def test_application_configuration_is_respected(self):
        handler = logging.NullHandler()
        self.logger.addHandler(handler)
        logs.ensure_configured(io.StringIO())
        self.assertEqual(self.logger.handlers, [handler])

    def test_engine_run_logs_to_stderr_stream_not_stdout(self):
        import contextlib
        stream, out = io.StringIO(), io.StringIO()
        logs.ensure_configured(stream)
        from core import engine
        from tests.fakes import FakeRuntime
        from runtime.base import BaseRuntime

        class Chatty(FakeRuntime):
            log = BaseRuntime.log
            phase = BaseRuntime.phase

        with contextlib.redirect_stdout(out):
            engine.run("q", runtime=Chatty(), config=Config(angles=2, votes_per_claim=1, refutations_required=1))
        self.assertEqual(out.getvalue(), "")
        self.assertIn("PHASE", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
