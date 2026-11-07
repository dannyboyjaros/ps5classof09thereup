#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print image dimensions using only the Python 2 standard library."""
from __future__ import print_function

import os
import struct
import sys


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


def main():
    for path in sys.argv[1:]:
        ext = os.path.splitext(path)[1].lower()
        try:
            size = png_size(path) if ext == ".png" else jpg_size(path)
        except Exception as err:
            size = "error: %s" % err
        print("%s %s" % (size, os.path.basename(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
