#!/usr/bin/env python3
"""Stop waiting after Wind/U reports that indexed colors are unavailable.

The vendor helper publishes colorMode=0, nClrStart=-1 on a 24-bit display.
Its property decoder returns false for that reply, so wudRunWUD waits for
ten seconds before taking its existing failure/true-color fallback.

Keep that return value and all color fields unchanged. A caller-saved ECX
flag distinguishes a complete unsupported-color reply from an absent or
incomplete reply. Only wudRunWUD consumes it, returning through its original
failure epilogue. Other callers retain the decoder's original return value.
Incomplete or incorrectly formatted properties now return false, rather
than interpreting stale fields after an unchecked sscanf.
"""

import argparse
import hashlib
from pathlib import Path
import shutil
import struct


ORIGINAL_SHA256 = "8ab13e18db4ff5285c484a494e1ff42cf4bec938a6fea58977a4aa3f4bea51e2"


def branch(opcode, address, destination):
    return opcode + struct.pack("<i", destination - address - len(opcode) - 4)


def patches():
    # These three ranges are alignment NOPs between hash-pinned functions.
    # No ELF layout, exported symbol, color field or original timeout changes.
    decode = 0x52984
    finish = 0x5CD05
    caller = 0x4A10F

    tail = bytes.fromhex(
        "48 83 bd e8 00 00 00 00"  # cmp qword [rbp+0xe8],0 (helper window)
        "74 14"                    # je restore
        "83 bd f0 00 00 00 00"     # cmp dword [rbp+0xf0],0 (colorMode)
        "75 0b"                    # jne restore
        "83 bd f4 00 00 00 ff"     # cmp dword [rbp+0xf4],-1 (nClrStart)
        "75 02"                    # jne restore
        "ff c1"                    # inc ecx: complete unsupported reply
    )
    restore = finish + len(tail)
    tail += bytes.fromhex("48 83 c4 58 89 d0 5b 5d c3")
    clear = finish + len(tail)
    tail += b"\x31\xc9" + branch(b"\xe9", clear + 2, restore)

    code = bytes.fromhex("89 c3 48 8b 7c 24 50")  # preserve sscanf count; data
    code += branch(b"\xe8", decode + len(code), 0x11A80)  # XFree
    code += bytes.fromhex(
        "31 c9 31 d2"              # completion flag=0; malformed result=0
        "83 fb 06 75 1d"           # require all six fields; otherwise return
        "83 7c 24 3c 08 75 16"     # require X property format 8
        "8b 95 f4 00 00 00"        # preserve original nClrStart>=0 result
        "f7 d2 c1 ea 1f"
        "83 7d 00 01 75 05"        # completion requires protocol version 1
    )
    code += branch(b"\xe9", decode + len(code), finish)
    code += branch(b"\xe9", decode + len(code), restore)

    loop = bytes.fromhex("85 c0 75 0d 85 c9")
    loop += branch(b"\x0f\x85", caller + len(loop), 0x451AF)
    loop += branch(b"\xe9", caller + len(loop), 0x4519A)
    loop += bytes.fromhex("83 bd f0 00 00 00 ff")
    loop += branch(b"\x0f\x85", caller + len(loop), 0x451C1)
    loop += branch(b"\xe9", caller + len(loop), 0x4519A)

    assert len(code) <= 60 and len(tail) <= 59 and len(loop) <= 49
    return [
        (decode, b"\x90" * len(code), code),
        (finish, b"\x90" * len(tail), tail),
        (caller, b"\x90" * len(loop), loop),
        # All decoder failure paths clear the caller-saved completion flag.
        (0x5CEBB, bytes.fromhex("48 83 c4 58 89"),
         branch(b"\xe9", 0x5CEBB, clear)),
        (0x5CF05, bytes.fromhex("48 8b 7c 24 50"),
         branch(b"\xe9", 0x5CF05, decode)),
        (0x4518D, bytes.fromhex("85 c0 74 09 83 bd f0 00 00 00 ff 75 27"),
         branch(b"\xe9", 0x4518D, caller) + b"\x90" * 8),
    ]


def patch(source, destination):
    if source.resolve() == destination.resolve():
        raise ValueError("input and output must be separate files")
    data = bytearray(source.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    if digest != ORIGINAL_SHA256:
        raise ValueError(f"unsupported libgdi50.so SHA-256: {digest}")
    for offset, original, replacement in patches():
        if data[offset:offset + len(original)] != original:
            raise ValueError(f"unexpected instructions at 0x{offset:x}")
        data[offset:offset + len(original)] = replacement
    with destination.open("xb") as output:
        output.write(data)
    shutil.copymode(source, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        patch(args.source, args.destination)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
