#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dump one label's node tree with important attributes."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex


def show_node(node, depth=0):
    kind = ex.tname(node)
    bits = []
    for name in ("name", "varname", "who", "what", "target", "label", "imspec", "line", "expr", "imgname"):
        if hasattr(node, name):
            value = getattr(node, name)
            if value is not None and value != "":
                bits.append("%s=%r" % (name, value))
    code = getattr(node, "code", None)
    if code is not None:
        src = getattr(code, "source", None)
        bits.append("code.source=%r" % (src,))
        bc = getattr(code, "bytecode", None)
        if bc is not None:
            bits.append("bytecode.len=%d" % (len(bc),))
    print("%s%s %s" % ("  " * depth, kind, " ".join(bits)))
    for name in ("block", "code_block"):
        child = getattr(node, name, None)
        if child:
            for item in child:
                show_node(item, depth + 1)
    for item in getattr(node, "items", None) or []:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            for child in item[2] or []:
                show_node(child, depth + 1)
    for item in getattr(node, "entries", None) or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            for child in item[-1] or []:
                show_node(child, depth + 1)


def main():
    path = os.path.abspath(sys.argv[1])
    wanted = sys.argv[2] if len(sys.argv) > 2 else None
    data, stmts = ex.read_rpyc(path)
    for node in stmts:
        if wanted is None or getattr(node, "name", None) == wanted:
            show_node(node)
    return 0


if __name__ == "__main__":
    sys.exit(main())
