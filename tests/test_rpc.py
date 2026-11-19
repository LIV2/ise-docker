import json
import os
import subprocess
import unittest


@unittest.skipUnless(os.environ.get("ISE_TEST_IMAGE"), "set ISE_TEST_IMAGE")
class RpcRuntimeTests(unittest.TestCase):
    def run_container(self, arguments, entrypoint="/usr/local/bin/ise-gui-entrypoint",
                      extra=(), network="none"):
        return subprocess.run(
            ["docker", "run", "--rm", "--init", "--platform", "linux/amd64",
             "--network", network, "--hostname", "ise", "--add-host", "ise:127.0.0.1",
             "--entrypoint", entrypoint, "-e", "ISE_GUI_UID=501",
             "-e", "ISE_GUI_GID=20", *extra, os.environ["ISE_TEST_IMAGE"],
             *arguments], capture_output=True, text=True, timeout=90)

    def test_rpc_ready_and_application_unprivileged(self):
        code = r'''
import json, os, pathlib, subprocess
assert (os.getuid(), os.getgid()) == (501, 20)
assert set(os.getgroups()) == {20, 30}
home = pathlib.Path.home()
assert home.stat().st_uid == 501
(home / 'ownership-check').write_text('ok')
assert (home / 'ownership-check').stat().st_uid == 501
assert all(p.stat().st_uid == 501 for p in home.rglob('*'))
status = pathlib.Path('/proc/self/status').read_text().splitlines()
assert int(next(s for s in status if s.startswith('CapEff:')).split()[1], 16) == 0
env = {k: v for k, v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'LD_PRELOAD')}
rpc = subprocess.run(['rpcinfo', '-p', '127.0.0.1'], env=env,
                     capture_output=True, text=True, check=True)
assert '100000' in rpc.stdout
processes = []
for p in pathlib.Path('/proc').glob('[0-9]*'):
    try:
        comm = (p / 'comm').read_text().strip()
        if comm == 'rpcbind':
            processes.append((p / 'status').read_text())
    except FileNotFoundError:
        pass
assert len(processes) == 1, processes
uid_line = next(s for s in processes[0].splitlines() if s.startswith('Uid:'))
assert int(uid_line.split()[1]) != 0, processes
print(json.dumps(dict(uid=os.getuid(), gid=os.getgid(), groups=os.getgroups(),
                      home=str(home), rpc_ready=True)))
'''
        result = self.run_container(["python3", "-c", code],
                                    extra=["-e", "ISE_GUI_GROUPS=20,30"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["rpc_ready"])

    def test_existing_portmapper_is_reused_and_status_preserved(self):
        code = r'''
/usr/local/bin/ise-start-rpcbind
before=$(pgrep -x rpcbind)
export EXPECTED_RPC_PID=$before
exec /usr/local/bin/ise-gui-entrypoint bash -c '
    test "$(pgrep -x rpcbind)" = "$EXPECTED_RPC_PID" || exit 90
    test "$(id -u)" = 501 || exit 91
    exit 23'
'''
        result = self.run_container(["-c", code], entrypoint="/bin/bash")
        self.assertEqual(result.returncode, 23, result.stderr)

    def test_old_nonroot_start_fails_with_actionable_message(self):
        result = self.run_container(["true"], extra=["--user", "501:20"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("updated xilinx-gui/run-docker launcher", result.stderr)

    def test_batch_does_not_start_rpc(self):
        result = self.run_container(
            ["bash", "-c", "if pgrep -x rpcbind; then exit 90; fi; exit 23"],
            entrypoint="/usr/local/bin/wrapper", extra=["--user", "501:20"])
        self.assertEqual(result.returncode, 23, result.stderr)

    def test_portmapper_rejects_nonloopback_clients(self):
        code = r'''
import os, subprocess
env = {k: v for k, v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'LD_PRELOAD')}
address = subprocess.check_output(['hostname', '-I'], env=env, text=True).split()[0]
local = subprocess.run(['rpcinfo', '-p', '127.0.0.1'], env=env, capture_output=True)
remote = subprocess.run(['rpcinfo', '-p', address], env=env, capture_output=True, timeout=5)
assert local.returncode == 0, local.stderr
assert remote.returncode != 0, remote.stdout
assert b'Authentication error' in remote.stderr, remote.stderr
'''
        result = self.run_container(["python3", "-c", code], network="bridge")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
