#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print the source text of Python nodes in a label."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex


def src_of(node):
    code = getattr(node, "code", None)
    if code is None:
        return None
    state = getattr(code, "_pickle_state", None)
    if state and len(state) >= 2:
        return state[1]
    return getattr(code, "source", None)


def main():
    path = os.path.abspath(sys.argv[1])
    label = sys.argv[2]
    data, stmts = ex.read_rpyc(path)

    def visit(node):
        kind = ex.tname(node)
        if kind == "Python":
            print("[python] %r" % (src_of(node),))
        elif kind == "Say":
            print("[say] %r %r" % (getattr(node, "who", None), getattr(node, "what", None)))
        elif kind in ("Show", "Scene", "Hide"):
            print("[%s] %r" % (kind, getattr(node, "imspec", None)))
        elif kind == "UserStatement":
            print("[user] %r" % (getattr(node, "line", None),))

    for node in stmts:
        if getattr(node, "name", None) == label:
            print("LABEL", label)
            ex.walk_nodes(node.block, visit)
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
