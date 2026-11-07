#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Detailed structural summary used while designing the runtime bytecode."""
from __future__ import print_function

import collections
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex


def main():
    game = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))
    if len(sys.argv) > 1:
        game = os.path.abspath(sys.argv[1])

    kinds = collections.Counter()
    menu_conds = collections.Counter()
    menu_sizes = collections.Counter()
    show_at = collections.Counter()
    show_layer = collections.Counter()
    user_cmds = collections.Counter()
    audio_channels = collections.Counter()
    audio_exts = collections.Counter()
    displays = collections.Counter()

    for name in ("script.rpyc", "options.rpyc", "screens.rpyc", "gui.rpyc"):
        path = os.path.join(game, name)
        if not os.path.isfile(path):
            continue
        data, stmts = ex.read_rpyc(path)

        def visit(node):
            kind = ex.tname(node)
            kinds[kind] += 1
            if kind == "Menu":
                items = getattr(node, "items", None) or []
                menu_sizes[len(items)] += 1
                for item in items:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        menu_conds[ex.as_text(item[1])] += 1
            if kind in ("Show", "Scene", "Hide"):
                imspec = getattr(node, "imspec", None)
                if imspec:
                    show_at[repr(imspec[3])] += 1
                    show_layer[repr(imspec[4])] += 1
            if kind == "UserStatement":
                line = ex.as_text(getattr(node, "line", "")) or ""
                parts = line.split()
                user_cmds[parts[0] if parts else ""] += 1
                if len(parts) > 1:
                    audio_channels[parts[1]] += 1
                for part in parts:
                    part = part.strip("\"'")
                    ext = os.path.splitext(part)[1].lower()
                    if ext:
                        audio_exts[ext] += 1
            if kind in ("Show", "Scene", "Hide") and ex.tname(node) == "Scene":
                pass

        ex.walk_nodes(stmts, visit)

    print("kinds", dict(kinds))
    print("menu item counts", dict(menu_sizes))
    print("menu conds", dict(menu_conds))
    print("show at_list", dict(show_at))
    print("show layer", dict(show_layer))
    print("user commands", dict(user_cmds))
    print("audio channels", dict(audio_channels))
    print("file extensions", dict(audio_exts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
