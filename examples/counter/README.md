# Counter build example

A four-bit synchronous counter for an XC9572XL CPLD. It exercises XST
synthesis, fitting and JEDEC generation without another repository or
board-specific source files. Both GUI and headless images can build it.

From this directory:

```sh
../../xilinx make
```

Output goes into `build/`, including `counter.jed`, `counter.rpt` and the
ISE project `counter.xise`. Use `../../xilinx make clean` to remove it.

The example has a 50 MHz clock constraint but no board pin assignments.
It is a toolchain check, not firmware to program onto an unspecified
board. Add the appropriate pin constraints before using real hardware.
