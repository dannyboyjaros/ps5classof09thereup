#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print Python/Define/Screen sources matching keywords."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def main():
    keywords = sys.argv[1:] or ["seekvoice", "def speak", "def setWait", "def setVoiceTrack"]
    for name in ("script.rpyc", "screens.rpyc", "options.rpyc", "gui.rpyc"):
        path = os.path.join(GAME, name)
        if not os.path.isfile(path):
            continue
        _, stmts = ex.read_rpyc(path)
        print("\n=== %s ===" % name)

        def visit(node):
            kind = ex.tname(node)
            src = ex.py_source(node)
            if src and any(k in src for k in keywords):
                print("--- %s ---" % kind)
                print(src)
            if kind == "Screen":
                print("--- Screen %r ---" % (getattr(node, "screen", None),))

        ex.walk_nodes(stmts, visit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
