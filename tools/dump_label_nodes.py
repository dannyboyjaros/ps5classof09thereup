#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print top-level nodes of one label with image/ATL details."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def walk_atl(block):
    out = []
    for st in ex.iter_atl_statements(block):
        exprs = []
        for item in getattr(st, "expressions", None) or []:
            exprs.append(ex.as_text(item[0] if isinstance(item, (list, tuple)) else item))
        out.append((getattr(st, "duration", None), getattr(st, "properties", None), exprs, getattr(st, "warper", None)))
    return out


def source_line(node):
    loc = getattr(node, "location", None) or getattr(node, "loc", None)
    if isinstance(loc, (list, tuple)) and len(loc) >= 2:
        return loc[-1]
    return None


def main():
    wanted = sys.argv[1] if len(sys.argv) > 1 else "scene_0002"
    tag = sys.argv[2] if len(sys.argv) > 2 else None
    _, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))
    active = [False]

    def visit(node):
        kind = ex.tname(node)
        if kind == "Label":
            active[0] = ex.as_text(getattr(node, "name", None)) == wanted
            if active[0]:
                print("=== label", wanted)
            return
        if not active[0]:
            return
        if kind in ("Show", "Scene", "Hide"):
            spec = getattr(node, "imspec", None)
            parts = " ".join(ex.as_text(p) for p in (spec[0] if spec else []) or [])
            t = ex.as_text(spec[2]) if spec and spec[2] else (ex.as_text(spec[0][0]) if spec and spec[0] else "")
            if tag and t != tag:
                return
            atl = getattr(node, "atl", None)
            print("%-6s line=%-6s %-28s tag=%-12s layer=%s" % (
                kind, source_line(node), parts, t, ex.as_text(spec[4]) if spec and spec[4] else "master"))
            if atl is not None:
                for row in walk_atl(atl):
                    print("        ", row)
        elif kind == "Say":
            if not tag:
                print("say    line=%-6s %r" % (source_line(node), ex.as_text(getattr(node, "what", ""))[:60]))

    ex.walk_nodes(stmts, visit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
