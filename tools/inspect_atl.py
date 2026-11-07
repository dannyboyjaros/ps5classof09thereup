#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inspect ATL blocks attached to show/scene nodes."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def walk(block):
    out = []
    for st in getattr(block, "statements", []) or []:
        if type(st).__name__ == "RawParallel":
            out.append(("PARALLEL", [walk(b) for b in getattr(st, "blocks", []) or []]))
        else:
            out.append((
                type(st).__name__,
                getattr(st, "duration", None),
                getattr(st, "properties", None),
                getattr(st, "expressions", None),
                getattr(st, "warper", None),
            ))
    return out


def main():
    _, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))
    found = [0]
    wanted = sys.argv[1] if len(sys.argv) > 1 else "0.1"

    def visit(node):
        if found[0] >= 8:
            return
        if ex.tname(node) not in ("Show", "Scene"):
            return
        atl = getattr(node, "atl", None)
        if atl is None or not hasattr(atl, "statements"):
            return
        tree = walk(atl)
        text = repr(tree)
        if wanted not in text:
            return
        found[0] += 1
        print("===", getattr(node, "imspec", None))
        for item in tree:
            print("   ", item)
        print("")

    ex.walk_nodes(stmts, visit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
