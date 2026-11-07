#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print ops between two indices or matching a tag."""
from __future__ import print_function

import io
import json
import sys


def main():
    if len(sys.argv) < 2:
        print("usage: dump_ops.py <label> [tag]")
        return 1
    name = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else None
    data = json.load(io.open("build/script.json", encoding="utf-8"))
    ops = data["ops"]
    start = data["labels"][name]
    end = len(ops)
    for other, idx in data["labels"].items():
        if idx > start and idx < end:
            end = idx
    for i in range(start, end):
        op = ops[i]
        if tag and not (op[0] in ("show", "hide", "scene") and len(op) > 2 and op[2] == tag):
            continue
        print("%5d  %s" % (i, op))
    return 0


if __name__ == "__main__":
    sys.exit(main())
