#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnostic helper: walk a .rpyc and report node classes/attributes."""
from __future__ import print_function

import collections
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex


def describe(value, limit=160):
    try:
        text = repr(value)
    except Exception:
        text = "<repr failed>"
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


def walk(nodes, depth=0, seen=None):
    if not nodes:
        return
    for node in nodes:
        kind = ex.tname(node)
        attrs = []
        for name in ("name", "who", "what", "target", "label", "imspec", "line", "varname"):
            if hasattr(node, name):
                attrs.append("%s=%s" % (name, describe(getattr(node, name))))
        print("%s%s %s" % ("  " * depth, kind, " ".join(attrs)))
        for name in ("block", "code_block"):
            child = getattr(node, name, None)
            if child:
                walk(child, depth + 1)
        entries = getattr(node, "entries", None)
        if entries:
            for entry in entries:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    walk(entry[-1], depth + 1)
        items = getattr(node, "items", None)
        if items:
            for item in items:
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    walk(item[2], depth + 1)


def main():
    path = sys.argv[1]
    data, stmts = ex.read_rpyc(path)
    print("version", data.get("version") if isinstance(data, dict) else data)
    counts = collections.Counter()
    ex.walk_nodes(stmts, lambda n: counts.update([ex.tname(n)]))
    print("counts", dict(counts))
    walk(stmts[:40] if len(sys.argv) < 3 else stmts[:int(sys.argv[2])])
    return 0


if __name__ == "__main__":
    sys.exit(main())
