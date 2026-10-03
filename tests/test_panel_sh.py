"""panel.sh must hand the question to Python as an argv element, never as code."""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "panel.sh")


@unittest.skipUnless(shutil.which("bash"), "bash required")
class PanelShTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", PANEL]).returncode, 0)

    def test_question_with_quotes_is_a_separate_argv_item(self):
        question = "it's \"quoted\"'); import os; os.system('touch PWNED') #"
        with tempfile.TemporaryDirectory() as tmp:
            stub = os.path.join(tmp, "python3")
            with open(stub, "w") as handle:
                handle.write('#!/bin/bash\nfor a in "$@"; do printf "%s\\0" "$a"; done > "$ARGV_OUT"\n')
            os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
            out = os.path.join(tmp, "argv")
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"],
                       DEEPSEEK_API_KEY="x", ARGV_OUT=out, HOME=tmp)
            proc = subprocess.run(["bash", PANEL, question], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "rb") as handle:
                argv = handle.read().decode().split("\0")[:-1]
        self.assertIn(question, argv)
        self.assertNotIn("-", argv[:1])  # stdin must stay free for the dashboard keyboard loop


if __name__ == "__main__":
    unittest.main()
