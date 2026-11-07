#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dump a screen's AST-ish structure by name."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def describe(value, depth=0, seen=None):
    if seen is None:
        seen = set()
    pad = "  " * depth
    if id(value) in seen:
        return
    seen.add(id(value))
    kind = type(value).__name__
    if isinstance(value, (str, int, float, bool, type(None))):
        print("%s%r" % (pad, value))
        return
    if isinstance(value, (list, tuple)):
        print("%s%s len=%d" % (pad, kind, len(value)))
        for item in value:
            describe(item, depth + 1, seen)
        return
    attrs = getattr(value, "__dict__", None)
    print("%s%s %r" % (pad, kind, value))
    if attrs:
        for key in sorted(attrs):
            print("%s  .%s =" % (pad, key))
            describe(attrs[key], depth + 2, seen)


def main():
    wanted = sys.argv[1] if len(sys.argv) > 1 else "say"
    _, stmts = ex.read_rpyc(os.path.join(GAME, "screens.rpyc"))

    def visit(node):
        if ex.tname(node) != "Screen":
            return
        scr = getattr(node, "screen", None)
        name = getattr(scr, "name", None) or getattr(scr, "screen_name", None)
        if name == wanted:
            print("=== screen", name, "===")
            describe(scr)
            print()
            describe(node)
            raise SystemExit(0)

    ex.walk_nodes(stmts, visit)
    print("screen not found:", wanted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
