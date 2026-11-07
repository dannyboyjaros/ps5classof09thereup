#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""One-off diagnostics for designing export format v2."""
from __future__ import print_function

import collections
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def label_summary(stmts):
    out = []
    for node in stmts:
        if ex.tname(node) != "Label":
            continue
        counts = collections.Counter()
        ex.walk_nodes(node.block, lambda n: counts.update([ex.tname(n)]))
        out.append((ex.as_text(getattr(node, "name", "")), counts))
    return out


def dump_node(node, depth=0):
    kind = ex.tname(node)
    bits = []
    for name in ("name", "varname", "who", "what", "target", "label", "imspec",
                 "line", "expr", "imgname", "code"):
        if not hasattr(node, name):
            continue
        value = getattr(node, name)
        if name == "code" and value is not None:
            bits.append("code=%r" % (getattr(value, "source", None),))
            continue
        if value not in (None, "", []):
            bits.append("%s=%r" % (name, value))
    print("%s%s %s" % ("  " * depth, kind, " ".join(bits)))
    for name in ("block", "code_block"):
        child = getattr(node, name, None)
        if child:
            for item in child:
                dump_node(item, depth + 1)
    for item in getattr(node, "items", None) or []:
        if isinstance(item, (list, tuple)):
            print("%s  menu-item text=%r cond=%r" % ("  " * depth, item[0], item[1]))
            for child in (item[2] or []):
                dump_node(child, depth + 2)
    for item in getattr(node, "entries", None) or []:
        if isinstance(item, (list, tuple)):
            print("%s  if-entry cond=%r" % ("  " * depth, item[0]))
            for child in (item[-1] or []):
                dump_node(child, depth + 2)


def main():
    for name in ("script.rpyc", "options.rpyc", "screens.rpyc", "gui.rpyc"):
        path = os.path.join(GAME, name)
        if not os.path.isfile(path):
            continue
        data, stmts = ex.read_rpyc(path)
        counts = collections.Counter()
        ex.walk_nodes(stmts, lambda n: counts.update([ex.tname(n)]))
        print("\n=== %s ===" % name)
        print("counts", dict(counts))
        if name == "script.rpyc":
            for label, lc in label_summary(stmts):
                special = [k for k in ("Menu", "If", "Screen", "With", "UserStatement", "Call") if lc.get(k)]
                if special:
                    print("label %-24s %s" % (label, dict(lc)))
            print("\n--- image defs ---")
            for node in stmts:
                ex.walk_nodes([node], lambda n: n)

    data, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))
    print("\n=== image defs in script ===")
    def visit_img(n):
        if ex.tname(n) == "Image":
            print("%r = %r" % (getattr(n, "imgname", None), ex.py_source(n)))
    ex.walk_nodes(stmts, visit_img)

    print("\n=== defines ===")
    def visit_def(n):
        if ex.tname(n) in ("Define", "Default"):
            print("%s %r = %r" % (ex.tname(n), getattr(n, "varname", None), ex.py_source(n)))
    ex.walk_nodes(stmts, visit_def)

    for wanted in ("start", "scene_0002", "end_0039"):
        print("\n=== label %s ===" % wanted)
        found = False
        for node in stmts:
            if ex.tname(node) == "Label" and ex.as_text(getattr(node, "name", "")) == wanted:
                found = True
                dump_node(node)
                break
        if not found:
            print("(not found)")

    print("\n=== endings files ===")
    endings = os.path.join(GAME, "endings")
    for name in sorted(os.listdir(endings)):
        print(repr(name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
