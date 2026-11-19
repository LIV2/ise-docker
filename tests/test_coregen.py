import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("ISE_TEST_IMAGE"), "requires an installed ISE image")
class CoregenTests(unittest.TestCase):
    def run_in_image(self, project, script):
        env = dict(os.environ, ISE_PROJECT_ROOT=str(project),
                   ISE_IMAGE=os.environ["ISE_TEST_IMAGE"])
        return subprocess.run(
            [str(ROOT / "xilinx"), "python3", "-c", script],
            cwd=project, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=600,
        )

    def test_fir_generation(self):
        # A help probe does not exercise CORE Generator's delivery of the
        # dependent HDL sources that XST needs to synthesize the core.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            run = """\
import os
from pathlib import Path
import shutil
source = (Path(os.environ["XILINX"]) /
          "sysgen/examples/coregen_import/example2/solution")
commands = (source / "fir_compiler_8tap.xco").read_text()
# Use a device actually present in the installed Virtex-6 database.
commands = commands.replace("xc6vcx240t", "xc6vlx75t")
commands = commands.replace("ff1156", "ff484")
commands = commands.replace(".\\\\fir_compiler_8tap.coe", "fir_compiler_8tap.coe")
Path("core.xco").write_text(commands)
options = [line for line in commands.splitlines() if line.startswith("SET ")]
Path("core.cgp").write_text("SET workingdirectory = .\\n" +
                            "\\n".join(options) + "\\n")
shutil.copy(source / "fir_compiler_8tap.coe", ".")
os.execvp("coregen", ["coregen", "-p", "core.cgp", "-b", "core.xco"])
"""
            result = self.run_in_image(project, run)
            self.assertEqual(result.returncode, 0, result.stdout)
            for name in ("fir_compiler_8tap.ngc", "fir_compiler_8tap.vhd"):
                output = project / name
                self.assertTrue(output.is_file(), result.stdout)
                self.assertGreater(output.stat().st_size, 0, result.stdout)

    def test_icon_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            run = r"""
import os
from pathlib import Path
source = (Path(os.environ["XILINX"]) /
          "coregen/ip/xilinx/network/com/xilinx/ip/srio_v5_6/delivery/"
          "example_design/chipscope/virtex6/verilog/srio_icon.xco")
commands = source.read_text().replace("xc6vlx240t", "xc6vlx75t")
commands = commands.replace("ff1156", "ff484")
Path("core.xco").write_text(commands)
options = [line for line in commands.splitlines() if line.startswith("SET ")]
Path("core.cgp").write_text("SET workingdirectory = .\n" +
                            "\n".join(options) + "\n")
os.execvp("coregen", ["coregen", "-p", "core.cgp", "-b", "core.xco"])
"""
            result = self.run_in_image(project, run)
            self.assertEqual(result.returncode, 0, result.stdout)
            output = project / "srio_icon.ngc"
            self.assertTrue(output.is_file(), result.stdout)
            self.assertGreater(output.stat().st_size, 0, result.stdout)

    def test_protected_hdl_preprocessing_and_integrity_rejection(self):
        # CORE Generator hides this child's exception and reports missing
        # HDL later. Test its normal API directly, including a damaged
        # library that must still be rejected by the original verifier.
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp)
                run = "CORRUPT = " + repr(corrupt) + r"""
import os
from pathlib import Path
root = Path(os.environ["XILINX"])
source = root / "coregen/ip/xilinx/dsp/com/xilinx/ip/xbip_utils_v2_0/bip_utils_pkg_v2_0.vhd"
if CORRUPT:
    data = bytearray((root / "lib/lin64/libisl_iostreams.so").read_bytes())
    # This byte is skipped by an unchanged jump destination. Corruption
    # must fail integrity verification without executing the changed byte.
    assert data[0xA472E6:0xA472E8] == b"\xeb\x03"
    data[0xA472E8] ^= 1
    folder = Path("corrupt").resolve()
    folder.mkdir()
    (folder / "libisl_iostreams.so").write_bytes(data)
    os.environ["LD_LIBRARY_PATH"] = str(folder) + ":" + os.environ["LD_LIBRARY_PATH"]
exe = str(root / "bin/lin64/unwrapped/xlicmgr")
os.execve(exe, [exe, "xlpp", str(source), "output.vhd"], os.environ)
"""
                result = self.run_in_image(project, run)
                output = project / "output.vhd"
                if corrupt:
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("Security failure", result.stdout)
                    self.assertFalse(output.exists(), result.stdout)
                else:
                    self.assertEqual(result.returncode, 0, result.stdout)
                    # The protected output changes between successful runs.
                    # FIR synthesis above verifies that XST can consume it.
                    data = output.read_bytes()
                    self.assertEqual(len(data), 20916)
                    self.assertTrue(data.startswith(b"XlxVHYEB"))
