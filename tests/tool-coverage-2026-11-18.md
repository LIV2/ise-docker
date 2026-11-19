# ISE 14.7 compatibility coverage

These checks ran on Apple Silicon macOS using Docker Desktop's
Linux/amd64 Rosetta translation. They establish tool startup and the
specific workflows below, not physical FPGA programming or complete
coverage of every GUI operation.

## Build and integrity regressions

The Rosetta patch accepts only the original `libisl_iostreams.so` SHA-256
`061e658034beae1ef5d3b6c9b6ad2092a464aa60b376184143ae0bdc0a145c56`.
The corrected output is
`c36110fd6d5c826e9397070c33e7a196623554b1fa0b3caf923a3f4bb1c16772`.

The patch retains the product, XOR and both rolling integrity checks,
including their original verification routines, expected values and
failure paths. A deliberately corrupted library is still rejected.
Earlier versions passed basic startup but failed FPGA MAP or omitted
CORE Generator HDL dependencies after a hidden preprocessing exception.

The corrected image passed:

- Native Spartan-3E MAP through the repository launcher.
- FIR generation, producing NGC and VHDL, in 17.97 seconds.
- ICON generation, producing NGC and Verilog, in 26.319 seconds.
- Direct protected HDL preprocessing through `xlicmgr xlpp`.
- A fresh XC9572XL counter synthesis, fit and JEDEC build.
- A clean pano-z80 synthesis, map, route and BitGen build. Its
  731,908-byte configuration payload exactly matched the original-library
  build, with SHA-256
  `d44e30604a598d69486b314e170c0b1335dcae362b1105bac114628579ea5c45`.

## Startup repairs

The initial sweep launched 146 entries from ISE/common `bin/lin64` and
identified 18 startup failures. Each reproduced with the original library,
separately from the CORE Generator regression. Their repairs and observed
results are listed below.

| Entrypoints | Repair and observed result |
| --- | --- |
| `fpga_editor`, `pace_old` | XPrint and bitmap fonts restore complete application windows |
| `timingan_cpld` | Complete window opens after acknowledging two warnings about the vendor's missing `timingan.map` context-help file |
| `xilhelp` | Loader enumeration and registry pointer fixes restore native help-map resolution and browser dispatch |
| `lmgrd`, `lmutil`, ISE/common `xilinxd` | LSB interpreter aliases restore native version queries |
| `smartxplorer` | 32-bit runtime restores native usage |
| `findmgsg` | 32-bit runtime restores invocation; unknown arguments return vendor status 1 without a loader error |
| `get_models`, `pr_verifyframes` | C-shell restores native usage |
| `mem_edit` | Complete Memory Editor and Memory Contents windows render |
| `getlibvers.pl` | Perl interpreter alias restores usage and real MAP module-version extraction |
| `ibertgenerate`, `ibertgengui`, `ibertplotter` | Bash restores native usage, the generation wizard and Plot Viewer |
| `zynqconfig_test` | Native self-test completes with 36 applied updates and 22 obsolete invalid inputs rejected; valid DDR changes and rejection preserving state are tested separately |

Only the Zynq self-test launcher loads its input adapter. Production
configuration tools continue to use the original library and rules.

## Wind/U startup and colors

GUI launchers initialize or reuse `rpcbind`, then drop to the caller's
UID/GID. The tests check supplementary groups, private-home ownership,
exit status, reuse of an existing portmapper and absence of RPC startup
for ordinary command-line builds.

A GUI-only adapter binds automatically created SunRPC TCP/UDP transports
to loopback. Raw RPC NULL calls reach the native registry and callback on
loopback and fail through the container's network address. Both ELF
classes are tested for transport creation, supplied sockets, failure
handling and file-descriptor ownership. RPC credentials and dispatch,
supplied sockets and ordinary `bind()` calls remain unchanged.

A separate color-handshake fix recognizes the helper's completed
`colorMode=0, nClrStart=-1` reply. It takes the existing true-color
fallback immediately, without advertising indexed colors or setting
`_wuWUDStarted` on a true-color display.

| PACE configuration | Original handshake | Fixed handshake |
| --- | ---: | ---: |
| 24-bit Xvfb | 11.946 s | 2.034 s |
| 8-bit Xvfb | 2.017 s | 1.982 s |

RGB screenshots and palette state matched exactly before and after at
each depth. Missing, partial and wrong-format replies retained the
original timeout; delayed replies waited for completion. Existing missing
toolbar icons in the 8-bit baseline were unchanged. The normal 24-bit
window rendered its toolbar.

A real 24-bit XQuartz check opened PACE in 2.285 seconds. A second paired
Xvfb run during image compilation measured 13.088 versus 3.281 seconds,
again with identical pixels and unchanged 8-bit behavior.

The color patch accepts only original `libgdi50.so` SHA-256
`8ab13e18db4ff5285c484a494e1ff42cf4bec938a6fea58977a4aa3f4bea51e2`
and produces
`5f94109571afe68407949e76d2dfd46dec74b1e9be37557879db78de95c7d784`.
The original library is retained beside the patched file.

## Basic help

Native `xilhelp -category topic -search contents isehelp` opens the
installed ISE Design Suite Overview in Dillo. The Netscape adapter also
accepts legacy `-remote openURL(...)` calls and opens direct RoboHelp HTML
topics. Relative links, Back and anchors were exercised in Dillo.

RoboHelp's JavaScript navigation, search and popups remain unsupported.
The absent CPLD context-help map is not reconstructed; its installed
manual topics can still be opened directly.

## Other functional checks

The earlier functional suite's 42 successful steps covered netgen Verilog
and VHDL exports; XDL round trips and DRC; power, IBIS and PROM exports;
part/speed queries; batch FPGA Editor loading; Verilog/VHDL ISim;
NGC/EDIF conversion; schematic and symbol conversions; iMPACT SVF output;
archive creation/extraction; CPLD timing/simulation/BSDL; and data2mem.
FIR and ICON regressions were added separately.

The Verilog and VHDL simulations reached the expected counter value.
PROM binary output matched the input configuration payload. iMPACT
produced an SVF containing scan operations through its file-output cable;
this was not hardware programming.

## Reproducing the checks

The standard-library unit suite needs no vendor files:

```sh
python3 -m unittest discover -s tests
```

Vendor cases skip unless their prerequisites are supplied. Set
`ISE_TEST_IMAGE` to a built ISE image and `ISE_LICENSE_FILE` to your
license for the integration tests. For example:

```sh
ISE_TEST_IMAGE=ise-14-7 ISE_LICENSE_FILE=/path/to/Xilinx.lic \
  python3 -m unittest discover -s tests -p test_fpga_map.py
```

Additional test inputs are:

- `ISE_TEST_LIBRARY`: original `libisl_iostreams.so`.
- `ISE_WINDU_ORIGINAL`: original `windu_registryd50`.
- `ISE_WINDU_GDI_ORIGINAL`: original `libgdi50.so`.
- `ISE_TEST_GUI_IMAGE`: a derivative with Xvfb, ImageMagick and GCC.
- `ISE_TEST_RPC_BUILD_IMAGE`: a derivative with GCC multilib and
  `libc6-dev-i386`, for both-architecture transport tests.

The final local run passed 21 tests and skipped 34 environment-gated
cases. Separate focused runs passed six RPC/MAP tests and nine
color/socket-adapter tests. Browser argument handling, real help dispatch
and rendered topics were checked separately. Test-only X servers,
ImageMagick and multilib compilers are not added to the production image.

Uncovered areas include physical USB/JTAG programming, a configured
FlexNet server, Mentor installation discovery and every GUI interaction.
Licensed features still require an appropriate license; no license files
or vendor executables are included in this repository.
