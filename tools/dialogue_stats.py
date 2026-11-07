#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report dialogue length statistics."""
from __future__ import print_function

import ast
import collections
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def main():
    _, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))
    lengths = []
    longest = [""]

    def visit(node):
        if ex.tname(node) != "Python":
            return
        src = (ex.py_source(node) or "").strip()
        if not src.startswith("speak("):
            return
        try:
            call = ast.parse(src).body[0].value
            text = ast.literal_eval(call.args[1])
        except Exception:
            return
        lengths.append(len(text))
        if len(text) > len(longest[1]):
            longest = (src, text)

    ex.walk_nodes(stmts, visit)
    lengths.sort()
    print("count", len(lengths), "min", lengths[0], "median", lengths[len(lengths) // 2],
          "p90", lengths[int(len(lengths) * 0.9)], "p99", lengths[int(len(lengths) * 0.99)],
          "max", lengths[-1])
    print("longest:", repr(longest[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
