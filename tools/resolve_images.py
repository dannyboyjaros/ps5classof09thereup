#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Resolve every show/scene/hide image spec to an actual file, and report sizes."""
from __future__ import print_function

import collections
import os
import re
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "Class of 09", "game"))

FLIP_RE = re.compile(r'im\.Flip\(\s*["\']([^"\']+)["\']')
MOVIE_RE = re.compile(r'Movie\s*\(\s*play\s*=\s*["\']([^"\']+)["\']')
SOLID_RE = re.compile(r'Solid\(\s*\(([^)]*)\)')


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != "\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def jpg_size(path):
    with open(path, "rb") as f:
        data = f.read()
    i = 2
    while i < len(data):
        if data[i] != "\xff":
            i += 1
            continue
        marker = ord(data[i + 1])
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        if marker in (0xD8, 0xD9):
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + length
    return None


def size_of(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        return png_size(path) if ext == ".png" else jpg_size(path)
    except Exception:
        return None


def main():
    index = {}
    for root, _, names in os.walk(GAME):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), GAME).replace("\\", "/")
            index[rel.lower()] = rel

    defs = {}
    specs = collections.Counter()
    layers = collections.Counter()
    _, stmts = ex.read_rpyc(os.path.join(GAME, "script.rpyc"))

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
                layers[repr(imspec[4])] += 1

    ex.walk_nodes(stmts, visit)

    print("layers", dict(layers))
    print("defs", len(defs), "specs", len(specs))
    unresolved = []

    def locate(name):
        name = name.replace("\\", "/")
        has_ext = os.path.splitext(name)[1].lower() in (".png", ".jpg", ".jpeg", ".webp")
        candidates = []
        if has_ext:
            candidates.append("images/" + name)
            candidates.append(name)
        else:
            for ext in (".png", ".jpg", ".jpeg"):
                candidates.append("images/" + name + ext)
            for ext in (".png", ".jpg", ".jpeg"):
                candidates.append(name + ext)
        for cand in candidates:
            key = cand.lower()
            if key in index:
                return index[key]
        return None

    for spec, count in specs.most_common():
        source = defs.get(spec)
        label = " ".join(spec)
        kind = "plain"
        flip = False
        movie = None
        solid = None
        rel = None
        if source:
            m = FLIP_RE.search(source)
            if m:
                kind = "flip"
                flip = True
                rel = locate(m.group(1))
            else:
                m = MOVIE_RE.search(source)
                if m:
                    kind = "movie"
                    movie = m.group(1)
                else:
                    m = SOLID_RE.search(source)
                    if m:
                        kind = "solid"
                        solid = m.group(1)
                    elif "im.Flip" in source:
                        kind = "flip-missed"
        if kind in ("plain", "flip-missed"):
            rel = locate(label)
            if not rel and not source:
                # try word order permutations (joined with space)
                words = list(spec)
                for i in range(len(words)):
                    rotated = words[i:] + words[:i]
                    rel = locate(" ".join(rotated))
                    if rel:
                        kind = "reordered"
                        break
        if kind == "plain" and source:
            kind = "defined-plain"

        dim = None
        if rel:
            dim = size_of(os.path.join(GAME, rel))
        print("%5d %-14s %-40s -> %-45s %s%s%s" % (
            count, kind, label, rel or (movie or solid or "??"),
            dim or "", " FLIP" if flip else "", " from=%r" % source[:70] if source else ""))
        if not rel and not movie and not solid:
            unresolved.append((label, count, source))

    print("\nUNRESOLVED", len(unresolved))
    for label, count, source in unresolved:
        print("%5d %r source=%r" % (count, label, source))
    return 0


if __name__ == "__main__":
    sys.exit(main())
