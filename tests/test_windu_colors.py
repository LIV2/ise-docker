"""Wind/U color negotiation: binary guards and real X11 startup behavior.

Set ISE_WINDU_GDI_ORIGINAL to the unmodified libgdi50.so. Set
ISE_TEST_GUI_IMAGE to an ISE image with Xvfb, ImageMagick, and gcc to run
the native tests. Each container uses its own X server and RPC services.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "patch_windu_colors", ROOT / "tools/patch-windu-colors.py")
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)
PATCHED_SHA256 = "5f94109571afe68407949e76d2dfd46dec74b1e9be37557879db78de95c7d784"
ORIGINAL = os.environ.get("ISE_WINDU_GDI_ORIGINAL")
GUI_IMAGE = os.environ.get("ISE_TEST_GUI_IMAGE")


class ColorPatchTests(unittest.TestCase):
    def test_unknown_image_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "original", Path(tmp) / "patched"
            source.write_bytes(b"unknown shared library")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                PATCH.patch(source, output)
            self.assertFalse(output.exists())

    @unittest.skipUnless(ORIGINAL, "requires the original libgdi50.so")
    def test_pinned_output_and_unchanged_source(self):
        source = Path(ORIGINAL)
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "patched"
            PATCH.patch(source, output)
            after = output.read_bytes()
            self.assertEqual(hashlib.sha256(after).hexdigest(), PATCHED_SHA256)
            self.assertEqual(len(before), len(after))
            self.assertEqual(output.stat().st_mode, source.stat().st_mode)
            self.assertEqual(source.read_bytes(), before)
            with self.assertRaises(FileExistsError):
                PATCH.patch(source, output)
            self.assertEqual(output.read_bytes(), after)

    @unittest.skipUnless(ORIGINAL, "requires the original libgdi50.so")
    def test_in_place_is_refused(self):
        source = Path(ORIGINAL)
        before = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "separate files"):
            PATCH.patch(source, source)
        self.assertEqual(source.read_bytes(), before)


# Observe the actual palette initialization outcome without wrapping the
# property decoder: its new caller-saved ECX flag must reach wudRunWUD.
PALETTE_TRACE = r'''
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
void wuInitSysPalette(void) {
    void (*real)(void) = dlsym(RTLD_NEXT, "wuInitSysPalette");
    real();
    int *started = dlsym(RTLD_NEXT, "_wuWUDStarted");
    int *uses = dlsym(RTLD_NEXT, "wubUsesPalettes");
    char *prop = dlsym(RTLD_NEXT, "_wudGlobalProp");
    if (started && uses && prop)
        fprintf(stderr, "PALETTE started=%d uses=%d mode=%d first=%d\n",
                *started, *uses, *(int *)(prop+0xf0), *(int *)(prop+0xf4));
}
'''


# Replace only the helper in fault-injection containers. The application,
# property decoder, polling loop, and X server remain native vendor code.
HELPER = r'''#!/usr/bin/python3
import ctypes as C
import os
import time

mode = os.environ['HELPER_MODE']
if mode == 'unresponsive':
    time.sleep(30)
else:
    x = C.CDLL('libX11.so.6')
    pointer, ulong, integer = C.c_void_p, C.c_ulong, C.c_int
    x.XOpenDisplay.argtypes = [C.c_char_p]
    x.XOpenDisplay.restype = pointer
    x.XDefaultRootWindow.argtypes = [pointer]
    x.XDefaultRootWindow.restype = ulong
    x.XInternAtom.argtypes = [pointer, C.c_char_p, integer]
    x.XInternAtom.restype = ulong
    x.XCreateSimpleWindow.argtypes = [pointer, ulong, integer, integer,
                                    C.c_uint, C.c_uint, C.c_uint, ulong, ulong]
    x.XCreateSimpleWindow.restype = ulong
    x.XChangeProperty.argtypes = [pointer, ulong, ulong, ulong, integer,
                                 integer, pointer, integer]
    x.XFlush.argtypes = [pointer]
    display = x.XOpenDisplay(None)
    assert display
    root = x.XDefaultRootWindow(display)
    atom = x.XInternAtom(display, b'ROOT_WUDATOMNAME', 0)
    window = x.XCreateSimpleWindow(display, root, 0, 0, 10, 10, 0, 0, 0)
    def publish(complete, format=8):
        value = ('1 ise Unknown_User %x 0' % window)
        if complete:
            value += ' -1'
        data = C.create_string_buffer(value.encode(), 248)
        x.XChangeProperty(display, root, atom, atom, format, 0,
                          data, 248 * 8 // format)
        x.XFlush(display)
    publish(mode == 'wrong_format', 16 if mode == 'wrong_format' else 8)
    if mode == 'delayed':
        time.sleep(2)
        publish(True)
    time.sleep(30)
'''


GUI_PROBE = r'''
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

root = Path('/test') / os.environ['CASE']
root.mkdir()
display = ':91'
env = dict(os.environ, HOME=str(root), DISPLAY=display,
           LD_PRELOAD='/test/palette-trace.so' +
           (':' + os.environ['LD_PRELOAD'] if os.environ.get('LD_PRELOAD') else ''))
server = subprocess.Popen(
    ['Xvfb', display, '-screen', '0', '1280x900x' + os.environ['DEPTH'],
     '-nolisten', 'tcp'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(.3)
app = None
try:
    with (root / 'output.log').open('w') as log:
        start = time.monotonic()
        app = subprocess.Popen(['pace_old'], env=env, cwd=root,
                               stdout=log, stderr=log, start_new_session=True)
        status = 'timeout'
        while time.monotonic() - start < 25:
            if app.poll() is not None:
                status = 'exit'
                break
            tree = subprocess.run(['xwininfo', '-display', display,
                                   '-root', '-tree'], capture_output=True,
                                  text=True).stdout
            if '"Xilinx PACE"' in tree and '890x508' in tree:
                status = 'window'
                break
            time.sleep(.1)
        elapsed = time.monotonic() - start
        time.sleep(.4)
        screenshot = root / 'screen.png'
        clean = ['env', '-u', 'LD_LIBRARY_PATH', '-u', 'LD_PRELOAD']
        subprocess.run(clean + ['import', '-display', display,
                               '-window', 'root', str(screenshot)], check=True)
        pixels = subprocess.check_output(clean + ['convert', str(screenshot),
                                                   '-depth', '8', 'rgb:-'])
        text = (root / 'output.log').read_text()
        palette = re.search(r'PALETTE started=(-?\d+) uses=(-?\d+) '
                            r'mode=(-?\d+) first=(-?\d+)', text)
        result = dict(case=os.environ['CASE'], status=status,
                      seconds=round(elapsed, 3), returncode=app.poll(),
                      palette=list(map(int, palette.groups())) if palette else None,
                      pixels=hashlib.sha256(pixels).hexdigest())
        (root / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
        assert status == 'window', text
finally:
    if app is not None and app.poll() is None:
        os.killpg(app.pid, signal.SIGKILL)
        app.wait()
    server.terminate()
    server.wait(timeout=10)
'''


@unittest.skipUnless(ORIGINAL and GUI_IMAGE,
                     "requires original libgdi50.so and an ISE GUI test image")
class ColorNegotiationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ise-windu-colors-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        # Native applications run as the invoking user's UID/GID.
        cls.uid, cls.gid = os.getuid(), os.getgid()
        PATCH.patch(Path(ORIGINAL), cls.root / "libgdi50.so")
        (cls.root / "palette-trace.c").write_text(PALETTE_TRACE)
        (cls.root / "gui.py").write_text(GUI_PROBE)
        (cls.root / "helper").write_text(HELPER)
        (cls.root / "helper").chmod(0o755)
        compiler = subprocess.run(
            ["docker", "run", "--rm", "--platform", "linux/amd64",
             "--network", "none", "--entrypoint", "bash", "-v",
             f"{cls.root}:/test", GUI_IMAGE, "-ec",
             "gcc -shared -fPIC -O2 -Wall -Wextra -Werror "
             "/test/palette-trace.c -o /test/palette-trace.so -ldl"],
            capture_output=True, text=True, timeout=30)
        if compiler.returncode:
            raise AssertionError(compiler.stdout + compiler.stderr)
        cases = [
            ("original24", 24, False, None),
            ("patched24", 24, True, None),
            ("original8", 8, False, None),
            ("patched8", 8, True, None),
            ("unresponsive", 24, True, "unresponsive"),
            ("partial", 24, True, "partial"),
            ("wrong_format", 24, True, "wrong_format"),
            ("delayed", 24, True, "delayed"),
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            cls.results = dict(pool.map(cls.run_case, cases))
        print(json.dumps(cls.results, sort_keys=True), flush=True)

    @classmethod
    def run_case(cls, case):
        name, depth, patched, helper = case
        command = [
            "docker", "run", "--rm", "--init", "--platform", "linux/amd64",
            "--network", "none", "--hostname", "ise",
            "--add-host", "ise:127.0.0.1", "--ulimit", "core=0",
            "--entrypoint", "/usr/local/bin/ise-gui-entrypoint",
            "-e", f"ISE_GUI_UID={cls.uid}", "-e", f"ISE_GUI_GID={cls.gid}",
            "-e", f"CASE={name}", "-e", f"DEPTH={depth}",
            "-v", f"{cls.root}:/test",
            "-v", f"{ROOT}/tools/start-rpcbind:/usr/local/bin/ise-start-rpcbind:ro",
            "-v", f"{ROOT}/tools/gui-entrypoint:/usr/local/bin/ise-gui-entrypoint:ro",
        ]
        vendor = "/opt/Xilinx/14.7/ISE_DS/ISE"
        library = cls.root / "libgdi50.so" if patched else Path(ORIGINAL)
        command += ["-v", f"{library}:{vendor}/lib/lin64/libgdi50.so:ro"]
        if helper:
            command += ["-e", f"HELPER_MODE={helper}", "-v",
                        f"{cls.root}/helper:{vendor}/bin/lin64/windu_clientd50:ro"]
        command += [GUI_IMAGE, "python3", "/test/gui.py"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise AssertionError(name + "\n" + result.stdout + result.stderr)
        return name, json.loads((cls.root / name / "result.json").read_text())

    def test_true_color_fallback_and_rendering_are_unchanged(self):
        before, after = self.results["original24"], self.results["patched24"]
        self.assertEqual(before["palette"], [0, 0, 0, -1])
        self.assertEqual(after["palette"], before["palette"])
        self.assertEqual(after["pixels"], before["pixels"])
        self.assertGreaterEqual(before["seconds"], 9.8)
        self.assertLess(after["seconds"], 8)
        self.assertGreater(before["seconds"] - after["seconds"], 7)

    def test_real_indexed_color_reply_and_rendering_are_unchanged(self):
        before, after = self.results["original8"], self.results["patched8"]
        self.assertEqual(before["palette"], [1, 0, 1, 80])
        self.assertEqual(after["palette"], before["palette"])
        self.assertEqual(after["pixels"], before["pixels"])
        self.assertLess(before["seconds"], 8)
        self.assertLess(after["seconds"], 8)

    def test_missing_and_malformed_replies_keep_the_timeout(self):
        for name in ("unresponsive", "partial", "wrong_format"):
            with self.subTest(reply=name):
                result = self.results[name]
                self.assertGreaterEqual(result["seconds"], 9.8)
                self.assertEqual(result["palette"][0], 0)

    def test_delayed_reply_waits_until_complete(self):
        result = self.results["delayed"]
        self.assertGreaterEqual(result["seconds"], 2)
        self.assertLess(result["seconds"], 8)
        self.assertEqual(result["palette"], [0, 0, 0, -1])


if __name__ == "__main__":
    unittest.main()
