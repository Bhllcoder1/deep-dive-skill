"""Dashboard regressions found in review: crash on first result, fake save, env mutation."""

import json
import os
import tempfile
import unittest
from unittest import mock

from core.dashboard import Dashboard, HistoryManager, PipelineController


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_render_after_external_result_does_not_crash(self):
        # panel.sh sets pipeline.result directly, so _last_question was never assigned.
        dash = Dashboard()
        dash.history = HistoryManager(os.path.join(self.tmp.name, "h.json"))
        dash.pipeline.result = {"summary": "s", "findings": [], "refuted": []}
        self.assertIn("Pipeline completed", dash.render())

    def test_save_report_writes_the_result(self):
        dash = Dashboard()
        path = os.path.join(self.tmp.name, "r.json")
        dash.save_report(path)  # nothing to save yet
        self.assertFalse(os.path.exists(path))
        dash.pipeline.result = {"summary": "s"}
        dash.save_report(path)
        with open(path) as handle:
            self.assertEqual(json.load(handle), {"summary": "s"})

    def test_pipeline_start_does_not_mutate_environment(self):
        controller = PipelineController()
        before = dict(os.environ)
        done = []
        with mock.patch("harness.deep_research", side_effect=lambda *a, **k: done.append(k) or {"summary": "x"}):
            controller.start("q", runtime="generic")
            controller._thread.join(5)
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(done[0]["runtime_name"], "generic")

    def test_cancelled_result_is_discarded(self):
        controller = PipelineController()

        def slow(*args, **kwargs):
            controller.stop()
            return {"summary": "late"}
        with mock.patch("harness.deep_research", side_effect=slow):
            controller.start("q")
            controller._thread.join(5)
        self.assertIsNone(controller.result)


if __name__ == "__main__":
    unittest.main()
