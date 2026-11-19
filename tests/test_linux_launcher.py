import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[1] / "run-docker"


class LinuxLauncherTests(unittest.TestCase):
    def test_ssh_display_private_cookie_and_cleanup_on_failure(self):
        with tempfile.TemporaryDirectory(prefix="ise gui ") as tmp:
            root = Path(tmp)
            (root / "RTL").mkdir()
            uname = root / "uname"
            uname.write_text("#!/bin/sh\necho Linux\n")
            uname.chmod(0o755)
            xauth = root / "xauth"
            xauth.write_text('''#!/usr/bin/env python3
import pathlib, sys
if sys.argv[1] == 'nlist':
    if sys.argv[2] == 'localhost:10.0':
        print('0100 test-cookie-record')
elif sys.argv[1] == '-f':
    pathlib.Path(sys.argv[2]).write_text(sys.stdin.read())
''')
            xauth.chmod(0o755)
            docker = root / "docker"
            docker.write_text('''#!/usr/bin/env python3
import json, pathlib, stat, sys
args=sys.argv[1:]
mount=next(a for a in args if ',dst=/tmp/ise.xauth,' in a)
path=pathlib.Path(mount.split('src=')[1].split(',dst=')[0])
print(json.dumps(dict(args=args, auth=str(path), cookie=path.read_text(),
                     mode=stat.S_IMODE(path.stat().st_mode))))
sys.exit(23)
''')
            docker.chmod(0o755)
            env = dict(os.environ, PATH=tmp + ":" + os.environ["PATH"],
                       DISPLAY="localhost:10.0",
                       ISE_XAUTH=str(xauth), ISE_PROJECT_ROOT="..",
                       ISE_IMAGE="gui-test", ISE_LICENSE_FILE="")
            result = subprocess.run([str(LAUNCHER), "ise", "project with spaces.xise"],
                                    cwd=root / "RTL", env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 23, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["mode"], 0o600)
            self.assertEqual(data["cookie"], "ffff test-cookie-record\n")
            self.assertFalse(Path(data["auth"]).exists())
            self.assertIn("DISPLAY=localhost:10.0", data["args"])
            self.assertIn(f"type=bind,src={root.resolve()},dst=/build", data["args"])
            self.assertIn("--init", data["args"])
            self.assertIn(f"ISE_GUI_UID={os.getuid()}", data["args"])
            self.assertIn(f"ISE_GUI_GID={os.getgid()}", data["args"])
            groups = next(arg for arg in data["args"] if arg.startswith("ISE_GUI_GROUPS="))
            self.assertIn(str(os.getgid()), groups.split("=", 1)[1].split(","))
            self.assertIn("/usr/local/bin/ise-gui-entrypoint", data["args"])
            self.assertEqual(data["args"][-3:],
                             ["gui-test", "ise", "project with spaces.xise"])

    def test_missing_cookie_fails_before_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in (("uname", "#!/bin/sh\necho Linux\n"),
                                  ("xauth", "#!/bin/sh\nexit 0\n")):
                path = Path(tmp) / name
                path.write_text(content)
                path.chmod(0o755)
            env = dict(os.environ, PATH=tmp + ":" + os.environ["PATH"], DISPLAY=":0",
                       ISE_PROJECT_ROOT=tmp)
            result = subprocess.run([str(LAUNCHER)], cwd=tmp, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("No authentication cookie", result.stderr)


if __name__ == "__main__":
    unittest.main()
