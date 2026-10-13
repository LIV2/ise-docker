#!/usr/bin/env python3
"""Move ISE 14.7's startup scratch variables off executable pages.

Accept only the measured Linux x86-64 library. Write a separate copy;
never modify an installed library implicitly or disable integrity checks.
"""

import argparse
import hashlib
from pathlib import Path
import shutil
import struct


ORIGINAL_SHA256 = "061e658034beae1ef5d3b6c9b6ad2092a464aa60b376184143ae0bdc0a145c56"
# (displacement offset, instruction end, original target, new target)
REFERENCES = (
    (0xA4731F, 0xA47327, 0xA46E5C, 0x427ED0),
    (0xA47358, 0xA4735C, 0xA46E5C, 0x427ED0),
    (0xA47376, 0xA4737A, 0xA46E5C, 0x427ED0),
    (0xA4741D, 0xA47421, 0xA46E6C, 0x427ED8),
    (0xA4742C, 0xA47430, 0xA46E68, 0x427ED4),
    (0xA47432, 0xA47436, 0xA46E6C, 0x427ED8),
    (0xA47438, 0xA4743C, 0xA46E6C, 0x427ED8),
    (0xA47447, 0xA4744B, 0xA46E68, 0x427ED4),
)
CHECK_START = 0xA46E70
CHECK_END = 0xAADC5C
BALANCE_WORD = 0xA46E74


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def product(data):
    """The affected range of the second integrity check, modulo 2**32."""
    value = 1
    for offset in range(CHECK_START, CHECK_END, 4):
        value = value * (u32(data, offset) | 1) & 0xFFFFFFFF
    return value


def patch(original):
    digest = hashlib.sha256(original).hexdigest()
    if digest != ORIGINAL_SHA256:
        raise ValueError(f"unsupported input SHA-256: {digest}")
    data = bytearray(original)
    for offset, end, old, new in REFERENCES:
        if end + struct.unpack_from("<i", data, offset)[0] != old:
            raise ValueError(f"unexpected instruction at {offset:#x}")
        struct.pack_into("<i", data, offset, new - end)

    # The 16-byte gap after .data precedes .bss at virtual address 0x427ee0.
    # Preserve both original initial state words. The checksum accumulator
    # is explicitly zeroed by the existing code before use.
    if any(data[0x227ED0:0x227EE0]):
        raise ValueError("data padding is not empty")
    data[0x227ED4:0x227EDC] = original[0xA46E68:0xA46E70]
    phoff = struct.unpack_from("<Q", data, 32)[0]
    data_header = phoff + 56
    if struct.unpack_from("<IIQQQQQQ", data, data_header) != (
        1, 7, 0x202000, 0x402000, 0x402000, 0x25ED0, 0x280E8, 0x200000
    ):
        raise ValueError("unexpected data segment layout")
    # Include the new initializers in the file-backed part of the mapping.
    # Neither .bss nor the segment's memory size moves. Data is now RW.
    struct.pack_into("<Q", data, data_header + 32, 0x25EDC)
    struct.pack_into("<I", data, data_header + 4, 6)

    # Error 103 is a *second* check: a product of (word | 1). Its range
    # includes the patched instructions, although the unpacker's initial
    # additive checksum does not. Balance their contribution in the unused
    # alignment word between the state constants and the first function.
    # All factors are odd and thus invertible modulo 2**32. Keep the
    # original expected checksum, comparison, and failure path unchanged.
    if u32(data, BALANCE_WORD) != 0:
        raise ValueError("code padding is not empty")
    factor = product(original) * pow(product(data), -1, 2**32) % 2**32
    struct.pack_into("<I", data, BALANCE_WORD, factor)
    if product(data) != product(original):
        raise ValueError("integrity checksum changed")
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        parser.error("destination already exists; use a new output path")
    try:
        result = patch(args.source.read_bytes())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    with args.destination.open("xb") as output:
        output.write(result)
    shutil.copymode(args.source, args.destination)
    print(f"{hashlib.sha256(result).hexdigest()}  {args.destination}")


if __name__ == "__main__":
    main()
