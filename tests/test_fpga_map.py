import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FpgaMapTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ISE_TEST_IMAGE"), "requires an installed ISE image")
    def test_spartan3e_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            shutil.copy(ROOT / "examples/counter/counter.v", project)
            (project / "map.tcl").write_text("""\
project new counter.xise
project set family Spartan3E
project set device xc3s1600e
project set package fg320
project set speed -5
xfile add counter.v
project set top counter
if {![process run "Map" -force rerun_all]} {exit 1}
project close
""")
            env = dict(os.environ, ISE_PROJECT_ROOT=tmp, ISE_IMAGE=os.environ["ISE_TEST_IMAGE"])
            # Exercise the native MAP binary with the current patch.
            # The former wrapper selected the original library and could
            # hide this regression from a successful project build.
            run = """\
import hashlib
import os
from pathlib import Path
root = Path(os.environ["XILINX"])
assert (root / "bin/lin64/unwrapped/map").read_bytes()[:4] == b"\\x7fELF"
library = (root / "lib/lin64/libisl_iostreams.so").read_bytes()
assert hashlib.sha256(library).hexdigest() == "c36110fd6d5c826e9397070c33e7a196623554b1fa0b3caf923a3f4bb1c16772"
os.execvp("xtclsh", ["xtclsh", "map.tcl"])
"""
            result = subprocess.run(
                [str(ROOT / "xilinx"), "python3", "-c", run],
                cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            # xtclsh can return zero after printing 'Process "Map" failed'.
            mapped = project / "counter_map.ncd"
            self.assertTrue(mapped.is_file(), result.stdout)
            self.assertGreater(mapped.stat().st_size, 0)
