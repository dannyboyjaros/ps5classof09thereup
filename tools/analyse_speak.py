#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Analyse speak()/setWait()/audio calls in the script."""
from __future__ import print_function

import ast
import collections
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex


def main():
    path = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game", "script.rpyc"))
    data, stmts = ex.read_rpyc(path)
    speakers = collections.Counter()
    issues = collections.Counter()
    flags = {"newlines": 0, "tags": 0}

    def visit(node):
        if ex.tname(node) != "Python":
            return
        src = (ex.py_source(node) or "").strip()
        if not src.startswith("speak("):
            return
        try:
            tree = ast.parse(src)
        except Exception as err:
            issues["parse"] += 1
            return
        call = tree.body[0].value
        if len(call.args) < 2:
            issues["args"] += 1
            return
        speakers[ast.dump(call.args[0])] += 1
        try:
            text = ast.literal_eval(call.args[1])
        except Exception:
            issues["text"] += 1
            return
        if "\n" in text:
            flags["newlines"] += 1
        if "{" in text or "}" in text:
            flags["tags"] += 1

    ex.walk_nodes(stmts, visit)
    print("speakers", dict(speakers))
    print("issues", dict(issues))
    print("newlines", flags["newlines"], "tags", flags["tags"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
