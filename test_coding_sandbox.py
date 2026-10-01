import os
import sys
import tempfile
import unittest
from pathlib import Path

from beldin.coding_sandbox import run


RUNTIME = Path(sys.executable).resolve().parent


class CodingSandboxTests(unittest.TestCase):
    @unittest.skipIf(
        os.environ.get('BELDIN_CODING_SANDBOX') == '1',
        'already inside coding AppContainer',
    )
    def test_temporary_directory_inside_appcontainer(self):
        with tempfile.TemporaryDirectory() as outer:
            workspace = Path(outer)

            (workspace / "test_inner_temp.py").write_text(
                "import pathlib,tempfile,unittest\n"
                "class InnerTempTest(unittest.TestCase):\n"
                "    def test_temporary_directory(self):\n"
                "        with tempfile.TemporaryDirectory() as d:\n"
                "            p=pathlib.Path(d)/'probe.txt'\n"
                "            p.write_text('sandbox-temp-ok',encoding='utf-8')\n"
                "            self.assertEqual(p.read_text(encoding='utf-8'),'sandbox-temp-ok')\n",
                encoding="utf-8",
            )

            result = run(
                RUNTIME,
                workspace,
                ["unittest", "discover", "-v"],
                timeout=10,
            )

            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(result["exit_code"], 0, result)


if __name__ == "__main__":
    unittest.main()
