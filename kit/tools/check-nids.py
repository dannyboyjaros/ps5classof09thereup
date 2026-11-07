#!/usr/bin/env python3
"""Report whether named symbols are exported by the clean-room libc.prx."""
import base64
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUFFIX = bytes([0x51, 0x8D, 0x64, 0xA6, 0x35, 0xDE, 0xD8, 0xC1,
                0xE6, 0xB0, 0x39, 0xB1, 0xC3, 0xE5, 0x52, 0x30])


def nid(name: str) -> str:
    digest = hashlib.sha1(name.encode() + SUFFIX).digest()
    return base64.b64encode(digest[:8][::-1]).decode()[:11].replace("/", "-")


def main(names: list[str]) -> int:
    exported = set()
    for line in (ROOT / "tooling/native/runtime/api-surface.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            exported.add(line.split("|")[0])
    for name in names:
        value = nid(name)
        print(f"{name:<22} {value:<12} {'IN' if value in exported else 'MISSING'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
