#!/usr/bin/env python3
"""Check that every libc NID imported by the converted app is exported by the
clean-room libc.prx (tooling/native/runtime/api-surface.txt).

Run from the kit after tools/build.sh has produced build/llvm-pie.elf and
build/eboot.elf. Requires llvm-readelf-18 on PATH.
"""
import base64
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUFFIX = bytes([0x51, 0x8D, 0x64, 0xA6, 0x35, 0xDE, 0xD8, 0xC1,
                0xE6, 0xB0, 0x39, 0xB1, 0xC3, 0xE5, 0x52, 0x30])
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def nid(name: str) -> str:
    digest = hashlib.sha1(name.encode() + SUFFIX).digest()
    return base64.b64encode(digest[:8][::-1]).decode()[:11].replace("/", "-")


def readelf(args: list[str]) -> str:
    return subprocess.check_output(["llvm-readelf-18", *args], text=True)


def dyn_undefined(path: pathlib.Path) -> list[str]:
    names = []
    for line in readelf(["--dyn-syms", str(path)]).splitlines():
        if " UND " in line:
            fields = line.split()
            if fields:
                names.append(fields[-1])
    return names


def main() -> int:
    plain = set(dyn_undefined(ROOT / "build/llvm-pie.elf"))
    by_nid = {nid(name): name for name in plain}

    needed = []
    for line in readelf(["-d", str(ROOT / "build/eboot.elf")]).splitlines():
        if "(NEEDED)" in line:
            needed.append(line.split("[")[1].split("]")[0])
    try:
        prefix = ALPHABET[needed.index("libSceLibcInternal.prx")]
    except ValueError:
        print("libSceLibcInternal.prx is not in the app's NEEDED list")
        return 1

    exported = set()
    for line in (ROOT / "tooling/native/runtime/api-surface.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            exported.add(line.split("|")[0])

    missing = []
    checked = 0
    for import_name in dyn_undefined(ROOT / "build/eboot.elf"):
        parts = import_name.split("#")
        if len(parts) < 2 or parts[1][:1] != prefix:
            continue
        value = parts[0]
        name = by_nid.get(value, "?")
        checked += 1
        if value not in exported:
            missing.append((name, value))
            print(f"{name:<22} {value:<12} MISSING")
    print(f"libc imports: {checked}  missing: {len(missing)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
