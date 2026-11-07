#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Categorise Python AST statements by the function they call."""
from __future__ import print_function

import collections
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex


CALL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_\.]*)\s*\(")


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
    calls = collections.Counter()
    samples = collections.defaultdict(list)
    others = collections.Counter()
    other_samples = collections.defaultdict(list)

    def visit(node):
        if ex.tname(node) != "Python":
            return
        src = (src_of(node) or "").strip()
        match = CALL_RE.match(src)
        if match:
            name = match.group(1)
            calls[name] += 1
            if len(samples[name]) < 3:
                samples[name].append(src)
        else:
            key = src.split("=")[0].strip() if "=" in src else src[:40]
            others[key] += 1
            if len(other_samples[key]) < 3:
                other_samples[key].append(src)

    ex.walk_nodes(stmts, visit)

    print("=== calls ===")
    for name, count in calls.most_common():
        print("%6d %s" % (count, name))
        for sample in samples[name]:
            print("        %r" % (sample[:180],))
    print("=== others ===")
    for key, count in others.most_common(60):
        print("%6d %r" % (count, key[:100]))
        for sample in other_samples[key]:
            print("        %r" % (sample[:180],))
    return 0


if __name__ == "__main__":
    sys.exit(main())
