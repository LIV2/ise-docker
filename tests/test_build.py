import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


BUILD = Path(__file__).resolve().parents[1] / "build"


class BuildTests(unittest.TestCase):
    def test_rosetta_opt_in_and_explicit_override(self):
        cases = (
            (None, [], []),
            ("1", [], ["ENABLE_ROSETTA_COMPATIBILITY=1"]),
            (None, ["--build-arg", "ENABLE_ROSETTA_COMPATIBILITY=1"],
             ["ENABLE_ROSETTA_COMPATIBILITY=1"]),
            ("1", ["--build-arg", "ENABLE_ROSETTA_COMPATIBILITY=0"],
             ["ENABLE_ROSETTA_COMPATIBILITY=1", "ENABLE_ROSETTA_COMPATIBILITY=0"]),
        )
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "docker"
            fake.write_text('#!/usr/bin/env python3\nimport json,sys\n'
                            'print(json.dumps(sys.argv[1:]))\n')
            fake.chmod(0o755)
            for setting, arguments, expected in cases:
                with self.subTest(setting=setting, arguments=arguments):
                    env = dict(os.environ, PATH=tmp + ":" + os.environ["PATH"])
                    env.pop("ENABLE_ROSETTA_COMPATIBILITY", None)
                    if setting is not None:
                        env["ENABLE_ROSETTA_COMPATIBILITY"] = setting
                    proc = subprocess.run(
                        [str(BUILD), "--build-arg", "ISE_BASE_IMAGE=existing-image",
                         "--build-arg", "ENABLE_GUI=0", *arguments],
                        env=env, capture_output=True, text=True, check=True)
                    argv = json.loads(proc.stdout)
                    self.assertEqual([arg for arg in argv
                                      if arg.startswith("ENABLE_ROSETTA_COMPATIBILITY=")],
                                     expected)
                    self.assertIn("ENABLE_GUI=0", argv)


if __name__ == "__main__":
    unittest.main()
