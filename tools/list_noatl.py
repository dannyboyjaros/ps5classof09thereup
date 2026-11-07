#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Summarise show/scene specs without an inline ATL block."""
from __future__ import print_function

import collections
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def main():
    _, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))
    count = collections.Counter()

    def visit(node):
        if ex.tname(node) not in ("Show", "Scene"):
            return
        if getattr(node, "atl", None) is not None:
            return
        spec = getattr(node, "imspec", None)
        if not spec:
            count["<scene clear>"] += 1
            return
        count[" ".join(ex.as_text(p) for p in spec[0])] += 1

    ex.walk_nodes(stmts, visit)
    for name, n in count.most_common():
        print("%4d %s" % (n, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
