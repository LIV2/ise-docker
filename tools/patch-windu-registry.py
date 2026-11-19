#!/usr/bin/env python3
"""Preserve cuserid's pointer width in ISE 14.7's Wind/U registry helper."""

import argparse
import hashlib
from pathlib import Path
import shutil


ORIGINAL_SHA256 = "c4ef012a9eb8c908180add559086e6cdd394b51f2e8022f591d07ece2998fdee"
OFFSET = 0xED3D
ORIGINAL = bytes.fromhex("48 63 d0")  # movsxd rdx, eax
FIXED = bytes.fromhex("48 89 c2")     # mov rdx, rax


def patch(source, destination):
    data = bytearray(source.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    if digest != ORIGINAL_SHA256:
        raise ValueError(f"unsupported windu_registryd50 SHA-256: {digest}")
    # cuserid returns a char pointer. The obsolete build treated it as an
    # implicit int, truncating a stack address before sprintf consumes it.
    if data[OFFSET - 5:OFFSET] != bytes.fromhex("e8 83 54 ff ff"):
        raise ValueError("unexpected cuserid call instruction")
    if data[OFFSET:OFFSET + len(ORIGINAL)] != ORIGINAL:
        raise ValueError("unexpected cuserid return conversion")
    data[OFFSET:OFFSET + len(FIXED)] = FIXED
    if source.resolve() == destination.resolve():
        raise ValueError("input and output must be separate files")
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
