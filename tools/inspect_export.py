#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inspect a generated format-v2 script.json."""
from __future__ import print_function

import collections
import io
import json
import sys


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "build/script.json"
    data = json.load(io.open(path, encoding="utf-8"))
    ops = data["ops"]
    kinds = collections.Counter(op[0] for op in ops)
    print("format", data.get("format"), "ops", len(ops), "labels", len(data["labels"]))
    print("start", data.get("start"))
    print("kinds:")
    for kind, n in kinds.most_common():
        print("  %-14s %d" % (kind, n))

    print("\nfirst 16 ops:")
    for op in ops[:16]:
        print("  ", op)

    print("\nlabel starts:")
    for name in ("start", "scene_0002", "scene_0003"):
        idx = data["labels"].get(name)
        if idx is None:
            continue
        print(" ", name, "@", idx)
        for op in ops[idx : idx + 10]:
            print("    ", op)

    voices = [op for op in ops if op[0] == "say" and op[5]]
    print("\nsay ops with voice:", len(voices))
    if voices:
        print("  ", voices[0])
    endings = [op for op in ops if op[0] == "ending"]
    print("ending ops:", len(endings), [op[1] for op in endings])
    movies = [op for op in ops if op[0] == "movie"]
    print("movie ops:", len(movies), movies[:4])
    menus = [op for op in ops if op[0] == "menu"]
    print("menus:", len(menus))
    if menus:
        m = menus[0]
        print("  choices:", [(c[0], c[2]) for c in m[1]])
    shows = [op for op in ops if op[0] in ("show", "scene")]
    print("\nsample show/scene:")
    for op in shows[:6]:
        print("  ", op)
    return 0


if __name__ == "__main__":
    sys.exit(main())
