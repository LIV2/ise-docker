import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "patch_windu_registry", ROOT / "tools/patch-windu-registry.py")
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


class RegistryPatchTests(unittest.TestCase):
    def test_unknown_image_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "original", Path(tmp) / "patched"
            source.write_bytes(b"unknown executable")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                PATCH.patch(source, output)
            self.assertFalse(output.exists())

    @unittest.skipUnless(os.environ.get("ISE_WINDU_ORIGINAL"),
                         "requires the original Wind/U registry helper")
    def test_only_pointer_conversion_changes(self):
        source = Path(os.environ["ISE_WINDU_ORIGINAL"])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "patched"
            PATCH.patch(source, output)
            before, after = source.read_bytes(), output.read_bytes()
            self.assertEqual(len(before), len(after))
            self.assertEqual(after[:PATCH.OFFSET], before[:PATCH.OFFSET])
            self.assertEqual(after[PATCH.OFFSET:PATCH.OFFSET + 3], PATCH.FIXED)
            self.assertEqual(after[PATCH.OFFSET + 3:], before[PATCH.OFFSET + 3:])
            self.assertEqual(output.stat().st_mode, source.stat().st_mode)
            with self.assertRaises(FileExistsError):
                PATCH.patch(source, output)
            self.assertEqual(output.read_bytes(), after)

    @unittest.skipUnless(os.environ.get("ISE_WINDU_ORIGINAL"),
                         "requires the original Wind/U registry helper")
    def test_in_place_is_refused(self):
        source = Path(os.environ["ISE_WINDU_ORIGINAL"])
        before = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "separate files"):
            PATCH.patch(source, source)
        self.assertEqual(source.read_bytes(), before)


class WinduEnumerationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ISE_TEST_IMAGE"),
                         "requires an installed ISE image")
    def test_real_libraries_are_enumerated_and_excluded(self):
        result = subprocess.run(
            ["docker", "run", "--rm", "--init", "--platform", "linux/amd64",
             "--network", "none", "-v", f"{ROOT}:/source:ro",
             os.environ["ISE_TEST_IMAGE"], "bash", "-ec", """\
gcc -O2 -Wall -Wextra -Werror /source/tests/fixtures/windu_enum_probe.c \\
    -o /tmp/enum-probe -ldl
LD_PRELOAD=/usr/local/lib/ise/xilhelp-compat.so /tmp/enum-probe
"""], capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS real library enumeration and exclusion", result.stdout)


class XilhelpMapTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ISE_TEST_GUI_IMAGE"),
                         "requires an ISE image with Xvfb")
    def test_native_help_map_dispatches_bundled_html(self):
        # The recording browser observes the native browser-launch boundary.
        # This verifies help resolution and dispatch, not HTML rendering.
        run = r'''
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    arguments = root / "browser-args"
    browser = Path("/usr/bin/firefox")
    assert not browser.exists(), "recording test requires no installed Firefox"
    browser.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "' + str(arguments) + '"\n')
    browser.chmod(0o755)
    env = dict(os.environ, DISPLAY=":96", HOME=tmp)
    server = subprocess.Popen(
        ["Xvfb", ":96", "-screen", "0", "1280x900x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    helper = None
    try:
        time.sleep(0.3)
        helper = subprocess.Popen(
            ["xilhelp", "-category", "topic", "-search", "contents", "isehelp"],
            env=env, cwd=tmp, start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        deadline = time.monotonic() + 110
        while time.monotonic() < deadline and not arguments.exists():
            if helper.poll() is not None:
                raise AssertionError(helper.communicate()[0])
            time.sleep(0.2)
        assert arguments.exists(), "native help did not dispatch to the browser"
        html = Path(os.environ["XILINX"]) / "doc/usenglish/isehelp/ise_c_overview.htm"
        assert html.is_file(), html
        assert arguments.read_text().strip() == "file://" + str(html), arguments.read_text()
        print("PASS native help map resolves and dispatches bundled overview")
    finally:
        if helper is not None and helper.poll() is None:
            os.killpg(helper.pid, signal.SIGTERM)
            helper.communicate(timeout=10)
        server.terminate()
        server.wait(timeout=10)
'''
        result = subprocess.run(
            ["docker", "run", "--rm", "--init", "--platform", "linux/amd64",
             "--network", "none", "--ulimit", "core=0",
             os.environ["ISE_TEST_GUI_IMAGE"], "python3", "-c", run],
            capture_output=True, text=True, timeout=140,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS native help map", result.stdout)
