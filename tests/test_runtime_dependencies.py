import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RuntimeDependencyTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ISE_TEST_IMAGE"), "requires an installed ISE image")
    def test_legacy_loaders_and_interpreters(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, ISE_PROJECT_ROOT=tmp,
                       ISE_IMAGE=os.environ["ISE_TEST_IMAGE"])
            run = """\
import ctypes
import os
from pathlib import Path
import subprocess

ctypes.CDLL("libXp.so.6")
root = Path(os.environ["XILINX"]) / "bin/lin64"
cases = [
    (["lmgrd", "-v"], 0, "v11.11"),
    (["lmutil", "lmver", str(root / "lmgrd")], 0, "FlexNet"),
    (["xilinxd", "-v"], 0, "v11.11"),
    ([str(Path(os.environ["XILINX"]).parent / "common/bin/lin64/xilinxd"), "-v"],
     0, "v11.11"),
    (["smartxplorer", "-help"], 0, "SmartXplorer"),
    (["get_models", "-help"], 0, "Usage: get_models"),
    (["pr_verifyframes", "-help"], 0, "pr_verifyframes version"),
    (["getlibvers.pl", "-help"], 33, "Generate a list of module versions"),
]
for command, code, message in cases:
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == code, (command, result.returncode, output)
    assert message.lower() in output.lower(), (command, output)
    print(command[0] + " ready")
# This helper has no help text and returns one for an unknown invocation. A
# loader failure instead returns 255 and names the missing interpreter.
result = subprocess.run(["findmgsg", "-help"], capture_output=True, timeout=10)
assert result.returncode == 1, (result.returncode, result.stderr)
assert not result.stderr, result.stderr
"""
            result = subprocess.run(
                [str(ROOT / "xilinx"), "python3", "-c", run],
                cwd=tmp, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stdout)

    @unittest.skipUnless(os.environ.get("ISE_TEST_GUI_IMAGE"),
                         "requires an ISE image with Xvfb")
    def test_memory_editor_opens(self):
        run = """\
import os
import signal
import subprocess
import tempfile
import time

with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, DISPLAY=":97", HOME=tmp)
    server = subprocess.Popen(
        ["Xvfb", ":97", "-screen", "0", "1280x900x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    editor = None
    try:
        time.sleep(0.3)
        editor = subprocess.Popen(
            ["mem_edit"], cwd=tmp, env=env, start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if editor.poll() is not None:
                raise AssertionError(editor.communicate()[0])
            windows = subprocess.run(
                ["xwininfo", "-root", "-tree"], env=env,
                capture_output=True, text=True, check=True,
            ).stdout
            if "Memory Editor - [definition1.cgf]" in windows:
                break
            time.sleep(0.5)
        else:
            raise AssertionError("Memory Editor did not open: " + windows)
    finally:
        if editor is not None and editor.poll() is None:
            os.killpg(editor.pid, signal.SIGTERM)
            editor.communicate(timeout=10)
        server.terminate()
        server.wait(timeout=10)
"""
        result = subprocess.run(
            ["docker", "run", "--rm", "--init", "--platform", "linux/amd64",
             "--network", "none", "--ulimit", "core=0",
             os.environ["ISE_TEST_GUI_IMAGE"], "python3", "-c", run],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
