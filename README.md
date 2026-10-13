# xilinx-ise

Xilinx ISE 14.7 in Docker, with command-line builds and optional X11 GUI
support on Linux and macOS.

## Build one image for CLI and GUI

The single `Dockerfile` uses Ubuntu 22.04 for both installation and runtime.
It installs from the vendor archive by default. Run:

```sh
# GUI enabled by default; Rosetta binary patch disabled.
./build

# Opt in to the Rosetta binary compatibility patch on Apple Silicon.
./build --build-arg ENABLE_ROSETTA_COMPATIBILITY=1

# CLI-only variant: skip the extra GUI packages and GUI fixes.
./build --build-arg ENABLE_GUI=0
```

If installer media is missing, `./build` opens the exact AMD download page.
Sign in and review AMD's address verification form, then click Download.
The helper watches `~/Downloads`, verifies AMD's checksum, imports the
completed archive, and continues the build. Subsequent builds reuse it.
This needs Python 3 on the host. [Manual download instructions](#manual-download)
and [helper options](#download-helper) are below.

These commands tag the result `ise-14-7`; choose one variant. To keep both,
use distinct tags with Docker directly:

```sh
docker build --platform linux/amd64 -t ise-14-7 .
docker build --platform linux/amd64 --build-arg ENABLE_GUI=0 \
    -t ise-14-7-nogui .
```

`ENABLE_GUI` accepts `1` (default) or `0`. Both variants use Ubuntu 22.04,
GNU make 4.3, and the same ISE and common files.
GUI support adds Java 8, GCC for ISim, X11 libraries, and ChipScope launcher
fixes. It does not start graphical applications during command-line builds.
Linux USB/JTAG support is included in both variants. PlanAhead and EDK
are not included.

An existing **unpatched** ISE installation image can optionally supply the
vendor files instead of running the installer:

```sh
./build --build-arg ISE_BASE_IMAGE=my-existing-ise-image
```

This overrides only the vendor-file source; the runtime is built by this
repository. No external ISE image is needed when using the installer archive.

## Optional Rosetta compatibility patch

`ENABLE_ROSETTA_COMPATIBILITY` is a Docker build argument accepting `0` (default)
or `1`. With `0`, the build leaves both `libisl_iostreams.so` files as
supplied by the installer or source image. With `1`, it applies the
version-specific [binary patch](tools/patch-iostreams.py),
accepts only the tested original library hash, and keeps each original
beside the patched file as `.so.original`. Invalid values fail the build.

The build wrapper also supports an environment-variable shortcut:

```sh
ENABLE_ROSETTA_COMPATIBILITY=1 ./build
# Both switches can be used together:
./build --build-arg ENABLE_ROSETTA_COMPATIBILITY=1 --build-arg ENABLE_GUI=0
```

An explicit `--build-arg ENABLE_ROSETTA_COMPATIBILITY=...` overrides the wrapper's
environment setting. Direct `docker build` invocations need the build
argument explicitly. There is no automatic host detection or runtime
patching; changing `docker run` environment variables does not change the
binaries.

The `ENABLE_` prefix is intentional: Rosetta rejects unknown `ROSETTA_`
environment variables before the translated build shell can start.

GUI support is independent of this option. Existing images retain their
previous patch state until rebuilt. The option defaults to off on Apple
Silicon too, where unpatched ISE startup can be very slow under Rosetta.

## Command-line builds

The image and ISE tools are **linux/amd64**. They run natively on x86-64
Linux. On Apple Silicon, enable Docker Desktop's Apple Virtualization
framework and Rosetta in [Docker's settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/).

Both `xilinx` and `xilinx-gui` default to the same `ise-14-7` image.
The launchers mount the enclosing Git repository, or the current directory
outside a Git checkout. `ISE_PROJECT_ROOT` overrides this selection.
`xilinx` uses your UID/GID and preserves
argument quoting and exit status. Docker's `--init` handles child-process
reaping and signal forwarding to the main process. Batch builds need no
terminal or display server, even with GUI support installed.

Run the included [counter example](examples/counter):

```sh
cd examples/counter
../../xilinx make
```

For your own project, run the launcher from that project's directory.
Sibling output directories within its Git checkout are available too:

```sh
cd /path/to/project/RTL
/path/to/ise-docker/xilinx make
```

Keep project sources, constraints, Makefiles and project-specific CI in
the project repository. This container supplies the tools and runs the
requested command; a failed synthesis or fit remains a failed build.

`ISE_IMAGE` selects another image, such as `ise-14-7-nogui`.
`ISE_LICENSE_FILE` optionally selects a host license file, mounted
read-only; otherwise the launcher uses `Xilinx.lic` beside the script if
present. Licenses are not packaged in the image.

### Install the launchers on PATH

After building the image, copy the self-contained host scripts to a
directory on your PATH:

```sh
mkdir -p ~/bin
cp xilinx xilinx-gui ~/bin/
chmod +x ~/bin/xilinx ~/bin/xilinx-gui
```

Then use `xilinx make` or `xilinx-gui ise project.xise` from any project.
The scripts require Docker; GUI use also needs the host X11 setup below.
Git is used to find the project root when available. Outside a checkout,
set `ISE_PROJECT_ROOT=..` if sibling directories must be mounted.
Set `ISE_LICENSE_FILE` to your license path, or put `Xilinx.lic` beside the
installed launchers. Copy updated scripts again after upgrading this repo.

## Graphical applications

Use the default GUI-enabled build and an X11 display server on the host.
The same commands work on Linux and macOS:

```sh
/path/to/ise-docker/xilinx-gui ise project.xise
/path/to/ise-docker/xilinx-gui coregen
```

With no arguments, `xilinx-gui` opens ISE. `ISE_PROJECT_ROOT`, `ISE_IMAGE`,
and `ISE_LICENSE_FILE` work as in the CLI launcher; `ISE_GUI_IMAGE` can
override the image for GUI use alone. An image built with `ENABLE_GUI=0`
rejects GUI launch with a message explaining how to enable support.

Only the selected display's authentication cookie is copied into a private
temporary file, mounted read-only and deleted on exit. No `xhost +` or
disabling authentication is needed. Project files persist in the mounted
directory; GUI preferences in the temporary container home are discarded
on exit.

With GUI enabled, the original JRE remains at
`ISE/java/lin64/jre.original`. ISim can use Lite mode without a full ISim
license; licensed features still require your license file.

### Linux: Xorg or XWayland

Install `xauth` on the host and run the launcher from your graphical
session, keeping its `DISPLAY` and, when set, `XAUTHORITY` environment.
The launcher uses host networking and mounts the local X11 socket directory
when present. This also supports an SSH-forwarded `DISPLAY`.

On a Wayland desktop, enable the compositor's XWayland support. ISE is an
X11 client: it uses `DISPLAY`, not `WAYLAND_DISPLAY`. [XWayland presents an
X11 server to these applications](https://wayland.freedesktop.org/docs/book/Xwayland.html).
A Wayland-only session without XWayland cannot display ISE.

### macOS: XQuartz

Install and start [XQuartz](https://www.xquartz.org/). In Settings → Security,
enable **Allow connections from network clients** and keep **Authenticate
connections** enabled, then quit and reopen XQuartz. The equivalent setting
is:

```sh
defaults write org.xquartz.X11 nolisten_tcp -bool false
```

The launcher finds the selected display and connects through
`host.docker.internal`, since Docker Desktop runs containers in a VM.

## GitHub Actions

Pushes and pull requests run shell syntax checks without proprietary
binaries. The manual [example workflow](.github/workflows/example.yml)
builds the counter included in this repository; it does not fetch an
external hardware project. Supply a reachable installed ISE image (either
variant, preferably by digest). The workflow runs on an x86-64 Ubuntu
runner and uploads the JEDEC file, reports and build log. It does not
publish images or create releases.

## Vendor installer files

You can download the installer manually or use the
[`download-installer`](download-installer) helper. Both paths use the same
vendor archive and Dockerfile; the original four-file installer remains
supported too.

### Manual download

1. Open [AMD's ISE 14.7 downloads page](https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/legacy-ise/v2012_4---14_7.html)
   and expand **ISE Design Suite – 14.7 – Oct 23, 2013**.
2. Choose **Full Installer for Linux** (about 6 GB), sign in to your AMD
   account, review the address verification form, and click **Download**.
   The [direct installer page](https://account.amd.com/en/forms/downloads/xef.html?filename=Xilinx_ISE_DS_Lin_14.7_1015_1.tar)
   skips the product menus.
3. Copy the downloaded archive into `xilinx-installer/`, keeping its name,
   then build from the repository directory:

```sh
cp ~/Downloads/Xilinx_ISE_DS_Lin_14.7_1015_1.tar xilinx-installer/
docker build --platform linux/amd64 -t ise-14-7 .
```

Add `--build-arg ENABLE_GUI=0` for a CLI-only image. You can also use
`./build` after copying the archive; it reuses the local file.

The checksum published by
[AMD](https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/legacy-ise/v2012_4---14_7.html)
is MD5 `e8065b2ffb411bb74ae32efa475f9817`; it is checked both on import and
inside the installer stage. This checks download integrity, not a digital
signature. Downloads use HTTPS.

### Download helper

Run `./download-installer` to prepare the media without starting a Docker
build, or run `./build` to prepare the media and build in one command. The
helper finds a completed archive in `~/Downloads`, verifies it, and copies
it into `xilinx-installer/` automatically. If no archive is available, it
opens the direct installer page and waits for the browser download.

AMD currently requires account sign-in and address verification before
issuing a download. The helper opens that exact page, avoiding navigation
through the product menus. It does not store credentials or submit your
address on your behalf. The browser handles that first authorization and
transfer; the script handles detection, verification, and caching. With
the archive cached in `xilinx-installer/`, no browser is needed again.

For an unattended transfer, put the **direct download URL issued by AMD**
in a private file outside this repository (the sign-in page URL will not
work):

```sh
./download-installer --url-file /private/path/amd-download-url.txt
./build
```

This uses curl, resumes partial transfers, retries transient failures, and
rejects a downloaded error/sign-in page. Signed URLs can expire; supply a
fresh one if needed. The URL is passed through stdin, not command-line
arguments, and is never put in an image. Keep the URL file private.

Other useful options:

```sh
./download-installer --downloads-dir /path/to/browser/downloads
./download-installer --from-file /path/to/Xilinx_ISE_DS_Lin_14.7_1015_1.tar
./download-installer --no-browser  # fail promptly if media is not available
```

### Original split installer

The original four split installer files are still supported when all are
present in `xilinx-installer/`:

- [Windows 7/XP/Server and Linux - Split Installer Base Image - File 1/4](https://www.xilinx.com/member/forms/download/xef.html?filename=Xilinx_ISE_DS_14.7_1015_1-1.tar)
- [Windows 7/XP/Server and Linux Install Data A - File 2/4](https://www.xilinx.com/member/forms/download/xef.html?filename=Xilinx_ISE_DS_14.7_1015_1-2.zip.xz)
- [Windows 7/XP/Server and Linux Install Data B - File 3/4](https://www.xilinx.com/member/forms/download/xef.html?filename=Xilinx_ISE_DS_14.7_1015_1-3.zip.xz)
- [Windows 7/XP/Server and Linux Install Data C - File 4/4](https://www.xilinx.com/member/forms/download/xef.html?filename=Xilinx_ISE_DS_14.7_1015_1-4.zip.xz)


Copy them into the repository and build:

```sh
cp ~/Downloads/Xilinx_ISE_DS_14.7_1015_* xilinx-installer/
./build
```

Installation invokes `batchxsetup` directly with `eula_accepted=Y` in
`files/tmp/install/config`, replacing the previous Expect dialogue.
Building accepts the installer EULAs, as the previous script did. The
installer files occupy several GB, so allow additional space for unpacking
and image layers. The build does not push an image.

## Linux X11 and USB/JTAG

Linux uses the same `ise-14-7` image. From your project directory:

```sh
/path/to/ise-docker/run-docker ise project.xise
/path/to/ise-docker/run-docker impact -batch program.cmd
```

With no arguments, `run-docker` opens a shell. It mounts the project at
`/build`, uses your UID/GID and supplementary groups, and accepts the same
`ISE_PROJECT_ROOT`, `ISE_IMAGE` and `ISE_LICENSE_FILE` settings as `xilinx`.
GUI applications require the default `ENABLE_GUI=1` build; batch iMPACT
also works in a headless image.

The launcher forwards the current X11 display with a temporary private
authentication cookie and mounts `/dev/bus/usb` when available. Host
networking also supports an SSH-forwarded display; `run-docker-ssh` is an
alias for this launcher. The host needs `xauth` when `DISPLAY` is set.

The image includes the [userspace Xilinx cable driver](https://github.com/dennisfen/xilinx-usb-driver),
`usbutils` and `fxload`. The `impact` launcher preloads the driver only for
iMPACT, leaving synthesis and other tools unaffected. The source and
`setup_pcusb` helper are in `/opt/xilinx-usb-driver`; vendor cable firmware
is in `/opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64`.

USB permissions and initial cable firmware loading must be configured on
the Linux host, following the driver's instructions. Container device
access does not replace host udev setup. Compilation and driver loading
can be checked without a cable; physical JTAG programming has not been
validated here. On macOS, use `xilinx` and `xilinx-gui`; these launchers do
not provide direct USB passthrough from macOS into Docker Desktop.
