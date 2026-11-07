#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""List show/scene ops for images whose source file is larger than 1080p."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex
import resolve_images

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def walk(block):
    out = []
    for st in getattr(block, "statements", []) or []:
        if type(st).__name__ == "RawParallel":
            out.extend(walk(b) for b in getattr(st, "blocks", []) or [])
        else:
            out.append((getattr(st, "duration", None), getattr(st, "properties", None), getattr(st, "expressions", None), getattr(st, "warper", None)))
    return out


def main():
    _, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))
    seen = set()

    def visit(node):
        if ex.tname(node) not in ("Show", "Scene"):
            return
        spec = getattr(node, "imspec", None)
        if not spec:
            return
        name = " ".join(ex.as_text(p) for p in spec[0])
        key = (name, repr(walk(node.atl)) if getattr(node, "atl", None) is not None else None)
        if key in seen:
            return
        seen.add(key)
        rel = "images/" + name + ".png"
        path = os.path.join(GAME, rel)
        if not os.path.isfile(path):
            rel = "images/" + name + ".jpg"
            path = os.path.join(GAME, rel)
        if not os.path.isfile(path):
            return
        dim = resolve_images.size_of(path)
        if not dim or (dim[0] <= 1920 and dim[1] <= 1080):
            return
        print("%-34s %s atl=%s" % (name, dim, walk(node.atl) if getattr(node, "atl", None) is not None else None))

    ex.walk_nodes(stmts, visit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
