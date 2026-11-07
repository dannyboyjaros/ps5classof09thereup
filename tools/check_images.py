#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check which show/scene image specs resolve to files on disk."""
from __future__ import print_function

import collections
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

FLIP_RE = re.compile(r'im\.Flip\(\s*["\']([^"\']+)["\']')
MOVIE_RE = re.compile(r'Movie\s*\(\s*play\s*=\s*["\']([^"\']+)["\']')
SOLID_RE = re.compile(r'Solid\(\s*\(([^)]*)\)')


def main():
    game = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))
    files = {}
    for root, _, names in os.walk(game):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), game).replace("\\", "/")
            files[rel.lower()] = rel
    data, stmts = ex.read_rpyc(os.path.join(game, "script.rpyc"))
    defs = {}
    specs = collections.Counter()

    def visit(node):
        kind = ex.tname(node)
        if kind == "Image":
            name = getattr(node, "imgname", None)
            if isinstance(name, (list, tuple)):
                name = tuple(ex.as_text(part) for part in name)
            defs[name] = ex.py_source(node) or ""
        elif kind in ("Show", "Scene", "Hide"):
            imspec = getattr(node, "imspec", None)
            if imspec and imspec[0]:
                specs[tuple(ex.as_text(part) for part in imspec[0])] += 1

    ex.walk_nodes(stmts, visit)

    unresolved = []
    for spec, count in specs.most_common():
        source = defs.get(spec)
        if source:
            flip = FLIP_RE.search(source)
            movie = MOVIE_RE.search(source)
            solid = SOLID_RE.search(source)
            continue
        joined = " ".join(spec)
        candidates = ["images/%s.png" % joined, "images/%s.jpg" % joined, "%s.png" % joined, "%s.jpg" % joined]
        if not any(c.lower() in files for c in candidates):
            unresolved.append((spec, count))

    print("total specs", len(specs), "unresolved", len(unresolved))
    for spec, count in unresolved:
        print("%4d %r" % (count, spec))
    print("defs", len(defs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
