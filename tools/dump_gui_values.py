#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dump Define/Default values from gui/options/screens."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def main():
    wanted = sys.argv[1:] or ["textbox", "name", "choice", "text_size", "font", "color",
                              "main_menu", "dialogue", "button", "menu"]
    for fname in ("gui.rpyc", "options.rpyc"):
        _, stmts = ex.read_rpyc(os.path.join(GAME, fname))
        print("\n=== %s ===" % fname)

        def visit(node):
            if ex.tname(node) in ("Define", "Default"):
                name = ex.as_text(getattr(node, "varname", "")) or ""
                src = ex.py_source(node) or ""
                if any(w in name.lower() or w in src.lower() for w in wanted):
                    print("%-40s = %s" % (name, src))

        ex.walk_nodes(stmts, visit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
