#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print unique UserStatement lines and With expressions."""
from __future__ import print_function

import collections
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def main():
    users = collections.Counter()
    withs = collections.Counter()
    _, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))

    def visit(node):
        kind = ex.tname(node)
        if kind == "UserStatement":
            users[ex.as_text(getattr(node, "line", ""))] += 1
        elif kind == "With":
            withs[ex.as_text(getattr(node, "expr", ""))] += 1
        elif kind == "Python":
            src = (ex.py_source(node) or "").strip()
            if not (src.startswith("speak(") or src.startswith("setWait(") or src.startswith("setVoiceTrack(")):
                users["[py] " + src.split("\n")[0][:90]] += 1

    ex.walk_nodes(stmts, visit)
    print("=== user statements ===")
    for line, count in users.most_common():
        print("%5d %r" % (count, line))
    print("\n=== with exprs ===")
    for expr, count in withs.most_common():
        print("%5d %r" % (count, expr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
