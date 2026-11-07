#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dump Style nodes with their property values."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))


def main():
    wanted = sys.argv[1:] or ["window", "namebox", "say_dialogue", "say_label", "choice_button",
                              "choice_button_text", "choice_vbox", "main_menu", "main_menu_vbox",
                              "main_menu_button", "main_menu_button_text"]
    for fname in ("gui.rpyc", "screens.rpyc"):
        path = os.path.join(GAME, fname)
        if not os.path.isfile(path):
            continue
        _, stmts = ex.read_rpyc(path)
        print("=== %s ===" % fname)

        def visit(node):
            if ex.tname(node) != "Style":
                return
            name = getattr(node, "name", None)
            if isinstance(name, (list, tuple)):
                name = " ".join(str(x) for x in name)
            name = ex.as_text(name)
            if name not in wanted:
                return
            print("--- style %s ---" % name)
            for attr in ("parent", "properties", "name"):
                print("  %s = %r" % (attr, getattr(node, attr, None)))
            print("  dict = %r" % (getattr(node, "__dict__", {}),))

        ex.walk_nodes(stmts, visit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
