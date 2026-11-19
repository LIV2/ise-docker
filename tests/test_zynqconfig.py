import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("ISE_TEST_IMAGE"),
                     "requires an installed ISE image")
class ZynqConfigTests(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run(
            ["docker", "run", "--rm", "--init", "--platform", "linux/amd64",
             "--network", "none", "--ulimit", "core=0", "-w", "/tmp",
             "-v", f"{ROOT}:/source:ro", os.environ["ISE_TEST_IMAGE"], *args],
            capture_output=True, text=True, timeout=60,
        )

    def test_help_and_bad_arguments(self):
        result = self.run_tool("zynqconfig_test", "-help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Usage: zynqconfig_test", result.stdout)
        self.assertNotIn("applied", result.stderr)
        result = self.run_tool("zynqconfig_test", "--unknown")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_vendor_self_test_completes(self):
        result = self.run_tool("zynqconfig_test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FPGA Speed", result.stdout)
        self.assertIn("ZynqConfig: Terminated", result.stdout)
        self.assertIn("applied 36 updates; rejected 22 invalid inputs", result.stderr)

    def test_valid_changes_and_invalid_width_preserve_state(self):
        result = self.run_tool("bash", "-ec", """\
gcc -O2 -Wall -Wextra -Werror /source/tests/fixtures/zynqconfig_probe.c \\
    -o /tmp/zynq-probe -ldl
LD_PRELOAD=/usr/local/lib/ise/zynqconfig-test-compat.so /tmp/zynq-probe
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS valid DDR updates and invalid-input rejection", result.stdout)
