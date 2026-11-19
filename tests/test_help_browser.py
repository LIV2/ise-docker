import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ADAPTER = Path(__file__).resolve().parents[1] / "tools/help-browser"


class HelpBrowserTests(unittest.TestCase):
    def invoke(self, *arguments):
        with tempfile.TemporaryDirectory(prefix="ise browser ") as tmp:
            root = Path(tmp)
            viewer = root / "viewer"
            viewer.write_text('''#!/usr/bin/env python3
import json, os, sys
print(json.dumps(dict(args=sys.argv[1:], preload=os.getenv('LD_PRELOAD'),
                     libraries=os.getenv('LD_LIBRARY_PATH'))))
sys.exit(23)
''')
            viewer.chmod(0o755)
            adapter = root / "adapter"
            adapter.write_text(ADAPTER.read_text().replace(
                'exec /usr/bin/dillo', 'exec "' + str(viewer) + '"'))
            env = dict(os.environ, LD_LIBRARY_PATH="/vendor/libraries",
                       LD_PRELOAD="/vendor/instrumentation.so")
            return subprocess.run(["bash", str(adapter), *arguments], env=env,
                                  capture_output=True, text=True)

    def test_plain_url_and_anchor_are_preserved(self):
        url = "file:///manual with spaces/topic.htm#section"
        result = self.invoke(url)
        self.assertEqual(result.returncode, 23, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["args"], [url])
        self.assertIsNone(data["libraries"])
        self.assertIsNone(data["preload"])

    def test_robohelp_topic_bypasses_javascript_frameset(self):
        result = self.invoke("-remote", 'openURL("file:///manual/start.htm#html/topic.htm#part",new-window)')
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(json.loads(result.stdout)["args"],
                         ["file:///manual/html/topic.htm#part"])

    def test_remote_data_is_never_evaluated(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "executed"
            url = f"file:///manual/$(touch {marker}).htm"
            result = self.invoke("-remote", f"openURL({url},new-tab)")
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(json.loads(result.stdout)["args"], [url])
            self.assertFalse(marker.exists())

    def test_unsupported_remote_command_is_rejected(self):
        result = self.invoke("-remote", "quit()")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
