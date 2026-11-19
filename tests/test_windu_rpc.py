"""Exercise the GUI-only RPC factories and the real Wind/U services.

ISE_TEST_RPC_BUILD_IMAGE needs gcc multilib; ISE_TEST_GUI_IMAGE needs Xvfb.
Both images need the integrated GUI entrypoint and RPC adapters.
"""
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOADER = "/usr/$LIB/ise-windu-rpc.so"
FACTORY_PROBE = r'''
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <unistd.h>

typedef void *(*buffered)(int, unsigned int, unsigned int);
typedef void *(*plain)(int);
static buffered tcp, udpbuf;
static plain udp;
static void *call(int kind, int fd) {
    if (kind == 0) return tcp(fd, 0, 0);
    if (kind == 1) return udp(fd);
    return udpbuf(fd, 8192, 8192);
}
static int address(int fd, unsigned long expected) {
    struct sockaddr_in a;
    socklen_t size = sizeof(a);
    return getsockname(fd, (struct sockaddr *)&a, &size) == 0 &&
           a.sin_family == AF_INET && ntohl(a.sin_addr.s_addr) == expected;
}
int main(int argc, char **argv) {
    tcp = dlsym(RTLD_DEFAULT, "svctcp_create");
    udp = dlsym(RTLD_DEFAULT, "svcudp_create");
    udpbuf = dlsym(RTLD_DEFAULT, "svcudp_bufcreate");
    if (!tcp || !udp || !udpbuf) return 10;
    if (argc > 1 && !strcmp(argv[1], "failure")) {
        int (*last_fd)(void) = dlsym(RTLD_DEFAULT, "last_factory_fd");
        if (!last_fd) return 11;
        for (int kind = 0; kind < 3; ++kind) {
            errno = 0;
            if (call(kind, -1) || errno != EIO) return 12;
            errno = 0;
            if (fcntl(last_fd(), F_GETFD) != -1 || errno != EBADF) return 13;
            int fd = socket(AF_INET, kind == 0 ? SOCK_STREAM : SOCK_DGRAM, 0);
            if (fd < 0) return 14;
            errno = 0;
            if (call(kind, fd) || errno != EIO || last_fd() != fd) return 15;
            if (fcntl(fd, F_GETFD) < 0 || !address(fd, INADDR_ANY)) return 16;
            close(fd);
        }
        puts("PASS factory failure ownership and errno");
        return 0;
    }
    for (int kind = 0; kind < 3; ++kind) {
        void *transport = call(kind, -1);
        if (!transport) return 20;
        /* xp_sock is the first int in both legacy SVCXPRT ABIs. */
        int fd = *(int *)transport;
        if (!address(fd, INADDR_LOOPBACK)) return 21;
    }
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in a = { .sin_family = AF_INET };
    if (bind(fd, (struct sockaddr *)&a, sizeof(a)) || !address(fd, INADDR_ANY)) return 22;
    void *transport = tcp(fd, 0, 0);
    if (!transport || *(int *)transport != fd || !address(fd, INADDR_ANY)) return 23;
    struct rlimit limit = {0, 0};
    if (setrlimit(RLIMIT_NOFILE, &limit)) return 24;
    errno = 0;
    if (tcp(-1, 0, 0) || errno != EMFILE) return 25;
    puts("PASS loopback factories, supplied socket and ordinary bind");
    return 0;
}
'''
FAILURE_PROVIDER = r'''
#include <errno.h>
static int latest;
int last_factory_fd(void) { return latest; }
void *svctcp_create(int fd, unsigned int send, unsigned int receive) {
    (void)send; (void)receive; latest = fd; errno = EIO; return 0;
}
void *svcudp_bufcreate(int fd, unsigned int send, unsigned int receive) {
    return svctcp_create(fd, send, receive);
}
void *svcudp_create(int fd) { return svctcp_create(fd, 0, 0); }
'''


class WinduRpcTests(unittest.TestCase):
    def run_container(self, code, *, gui=False, timeout=60):
        image = os.environ.get("ISE_TEST_GUI_IMAGE" if gui else "ISE_TEST_RPC_BUILD_IMAGE")
        if not image:
            self.skipTest("requires an installed ISE test image")
        return subprocess.run(
            ["docker", "run", "--rm", "--init", "--platform", "linux/amd64",
             "--network", "bridge", "--hostname", "ise", "--add-host", "ise:127.0.0.1",
             "--ulimit", "core=0", "--entrypoint", "/usr/local/bin/ise-gui-entrypoint",
             "-e", "ISE_GUI_UID=501", "-e", "ISE_GUI_GID=20",
             image, "python3", "-c", code],
            capture_output=True, text=True, timeout=timeout,
        )

    def test_factories_both_architectures(self):
        code = f"""\
import os, pathlib, subprocess, tempfile
probe = {FACTORY_PROBE!r}
failure = {FAILURE_PROVIDER!r}
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    (root / 'probe.c').write_text(probe)
    (root / 'failure.c').write_text(failure)
    clean = dict(os.environ)
    clean.pop('LD_PRELOAD', None)
    for bits in (64, 32):
        executable = str(root / ('probe' + str(bits)))
        library = str(root / ('failure' + str(bits) + '.so'))
        common = ['gcc', '-m' + str(bits), '-O2', '-Wall', '-Wextra', '-Werror']
        subprocess.run(common + [str(root / 'probe.c'), '-o', executable, '-ldl'], env=clean, check=True)
        subprocess.run(common + ['-shared', '-fPIC', str(root / 'failure.c'), '-o', library], env=clean, check=True)
        for mode in ('real', 'failure'):
            preload = {LOADER!r} + (':' + library if mode == 'failure' else '')
            result = subprocess.run([executable, mode], env=dict(clean, LD_PRELOAD=preload), capture_output=True, text=True)
            assert result.returncode == 0, (bits, mode, result.returncode, result.stdout, result.stderr)
            assert 'wrong ELF class' not in result.stderr, result.stderr
            print(bits, mode, result.stdout.strip())
"""
        result = self.run_container(code)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("32 failure PASS", result.stdout)
        self.assertIn("64 real PASS", result.stdout)

    def test_native_tcp_and_udp_are_loopback_only(self):
        code = r'''
import errno, json, os, pathlib, signal, socket, struct, subprocess, time
clean = {k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD', 'LD_LIBRARY_PATH')}
address = subprocess.check_output(['hostname', '-I'], env=clean, text=True).split()[0]
env = dict(os.environ, DISPLAY=':93')
server = subprocess.Popen(['Xvfb', ':93', '-screen', '0', '1280x900x24', '-nolisten', 'tcp'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
app = None
log_path = pathlib.Path(os.environ['HOME']) / 'pace-rpc-test.log'
log = log_path.open('w')
try:
    time.sleep(.3)
    app = subprocess.Popen(['pace_old'], cwd=os.environ['HOME'], env=env, start_new_session=True, stdout=log, stderr=subprocess.STDOUT, text=True)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        assert app.poll() is None, log_path.read_text()
        windows = subprocess.check_output(['xwininfo', '-display', ':93', '-root', '-tree'], env=env, text=True)
        if '"Xilinx PACE"' in windows and '890x508' in windows:
            break
        time.sleep(.2)
    else:
        raise AssertionError('PACE main window did not open')
    table = subprocess.check_output(['rpcinfo', '-p', '127.0.0.1'], env=clean, text=True)
    rows = [line.split() for line in table.splitlines()[1:]]
    tcp = next(row for row in rows if row[0] != '100000' and row[1:3] == ['2','tcp'])
    udp = next(row for row in rows if row[0] != '100000' and row[2] == 'udp')
    def request(row, host):
        program, version, protocol, port = row[:4]
        call = struct.pack('!10I', 0x12345678, 0, 2, int(program), int(version), 0, 0, 0, 0, 0)
        kind = socket.SOCK_STREAM if protocol == 'tcp' else socket.SOCK_DGRAM
        with socket.socket(socket.AF_INET, kind) as connection:
            connection.settimeout(1)
            connection.connect((host, int(port)))
            if protocol == 'tcp':
                connection.sendall(struct.pack('!I', 0x80000000 | len(call)) + call)
                header = connection.recv(4)
                length = struct.unpack('!I', header)[0] & 0x7fffffff
                response = b''
                while len(response) < length:
                    chunk = connection.recv(length-len(response))
                    assert chunk, 'truncated RPC response'
                    response += chunk
            else:
                connection.send(call)
                response = connection.recv(4096)
        assert struct.unpack('!6I', response) == (0x12345678, 1, 0, 0, 0, 0), response.hex()
    for row in (tcp, udp):
        request(row, '127.0.0.1')
        try:
            request(row, address)
        except OSError as error:
            assert isinstance(error, TimeoutError) or error.errno == errno.ECONNREFUSED, error
        else:
            raise AssertionError('native RPC accepted a nonloopback request: ' + str(row))
        entries = pathlib.Path('/proc/net/' + row[2]).read_text().splitlines()[1:]
        port = '%04X' % int(row[3])
        listeners = [line.split()[1] for line in entries if line.split()[1].endswith(':' + port)]
        assert listeners and all(item.startswith('0100007F:') for item in listeners), listeners
    print('PASS native PACE startup and raw TCP/UDP loopback RPC', json.dumps([tcp, udp]))
finally:
    if app is not None and app.poll() is None:
        os.killpg(app.pid, signal.SIGTERM)
        try:
            app.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(app.pid, signal.SIGKILL)
            app.wait(timeout=5)
    log.close()
    server.terminate()
    server.wait(timeout=5)
'''
        result = self.run_container(code, gui=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS native PACE startup", result.stdout)
        self.assertNotIn("wrong ELF class", result.stderr)


if __name__ == "__main__":
    unittest.main()
