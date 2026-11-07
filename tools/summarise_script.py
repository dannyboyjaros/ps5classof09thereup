#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Summarise images, ifs, menus and user statements in a .rpyc."""
from __future__ import print_function

import collections
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
    data, stmts = ex.read_rpyc(path)
    images = set()
    imspecs = collections.Counter()
    ifs = []
    users = collections.Counter()
    image_stmts = []

    def visit(node):
        kind = ex.tname(node)
        if kind in ("Show", "Scene", "Hide"):
            imspec = getattr(node, "imspec", None)
            imspecs[repr(imspec[0] if imspec else None)] += 1
        if kind == "Image":
            image_stmts.append((getattr(node, "imgname", None), src_of(node)))
        if kind == "If":
            entries = []
            for entry in getattr(node, "entries", None) or []:
                entries.append((ex.as_text(entry[0]), len(entry[1] or [])))
            ifs.append(entries)
        if kind == "UserStatement":
            line = ex.as_text(getattr(node, "line", "")) or ""
            users[line.split()[0] if line.split() else ""] += 1

    ex.walk_nodes(stmts, visit)
    print("=== distinct imspecs ===")
    for name, count in imspecs.most_common():
        print("%5d %s" % (count, name))
    print("=== image statements ===")
    for name, src in image_stmts:
        text = ex.as_text(src) or ""
        print("%r -> %r" % (name, text[:200]))
    print("=== ifs ===")
    for entries in ifs:
        print(entries)
    print("=== user statement verbs ===")
    for name, count in users.most_common():
        print("%5d %s" % (count, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
