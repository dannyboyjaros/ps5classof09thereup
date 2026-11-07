#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dump menu items and if conditions."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def main():
    _, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))
    current = [None]

    def visit(node):
        kind = ex.tname(node)
        if kind == "Label":
            current[0] = ex.as_text(getattr(node, "name", ""))
        elif kind == "Menu":
            print("\n%s MENU" % current[0])
            for item in getattr(node, "items", None) or []:
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    print("  %r cond=%r" % (ex.as_text(item[0]), ex.as_text(item[1])))
        elif kind == "If":
            print("\n%s IF" % current[0])
            for entry in getattr(node, "entries", None) or []:
                print("  cond=%r" % (ex.as_text(entry[0]),))

    ex.walk_nodes(stmts, visit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
