import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[1] / "xilinx"


class LauncherTests(unittest.TestCase):
    def test_batch_mounts_parent_and_preserves_arguments_and_status(self):
        with tempfile.TemporaryDirectory(prefix="ise launcher ") as tmp:
            root = Path(tmp)
            (root / "RTL").mkdir()
            (root / "bin").mkdir()
            fake = root / "bin/docker"
            fake.write_text('#!/usr/bin/env python3\nimport json,sys\n'
                            'print(json.dumps(sys.argv[1:]))\nsys.exit(23)\n')
            fake.chmod(0o755)
            env = dict(os.environ, PATH=str(root / "bin") + ":" + os.environ["PATH"],
                       ISE_PROJECT_ROOT="..", ISE_IMAGE="test-image", ISE_LICENSE_FILE="")
            proc = subprocess.run([str(LAUNCHER), "xtclsh", "file with spaces.tcl", "a*b"],
                                  cwd=root / "RTL", env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 23, proc.stderr)
            argv = json.loads(proc.stdout)
            self.assertEqual(argv[-4:], ["test-image", "xtclsh", "file with spaces.tcl", "a*b"])
            self.assertIn("-i", argv)
            self.assertIn("--init", argv)
            self.assertNotIn("-it", argv)
            self.assertEqual(argv[argv.index("--workdir") + 1], "/build/RTL")
            self.assertIn(f"type=bind,src={root.resolve()},dst=/build", argv)

    def test_git_root_mounts_sibling_outputs_without_an_override(self):
        with tempfile.TemporaryDirectory(prefix="ise launcher ") as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "RTL").mkdir()
            (root / "bin").mkdir()
            fake = root / "bin/docker"
            fake.write_text('#!/usr/bin/env python3\nimport json,sys\n'
                            'print(json.dumps(sys.argv[1:]))\nsys.exit(23)\n')
            fake.chmod(0o755)
            env = dict(os.environ, PATH=str(root / "bin") + ":" + os.environ["PATH"],
                       ISE_IMAGE="test-image", ISE_LICENSE_FILE="")
            env.pop("ISE_PROJECT_ROOT", None)
            proc = subprocess.run([str(LAUNCHER), "xtclsh", "file with spaces.tcl", "a*b"],
                                  cwd=root / "RTL", env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 23, proc.stderr)
            argv = json.loads(proc.stdout)
            self.assertEqual(argv[-4:], ["test-image", "xtclsh", "file with spaces.tcl", "a*b"])
            self.assertIn("-i", argv)
            self.assertIn("--init", argv)
            self.assertNotIn("-it", argv)
            self.assertEqual(argv[argv.index("--workdir") + 1], "/build/RTL")
            self.assertIn(f"type=bind,src={root.resolve()},dst=/build", argv)

    def test_missing_license_fails_before_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, ISE_LICENSE_FILE=tmp + "/missing.lic", ISE_PROJECT_ROOT=tmp)
            proc = subprocess.run([str(LAUNCHER), "true"], cwd=tmp, env=env,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("License file does not exist", proc.stderr)


if __name__ == "__main__":
    unittest.main()
