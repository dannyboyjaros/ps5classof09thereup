#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sample average colours from a PNG."""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import png_bbox


def main():
    for path in sys.argv[1:]:
        width, height, px = png_bbox.load_rgba(path)
        regions = [
            ("center", width // 2 - 100, height // 2 - 40, width // 2 + 100, height // 2 + 40),
            ("top-left", 200, 20, 500, 120),
            ("bottom", width // 2 - 100, height - 60, width // 2 + 100, height - 10),
        ]
        print(path.split("\\")[-1], "%dx%d" % (width, height))
        for name, x0, y0, x1, y1 in regions:
            x1 = min(x1, width)
            y1 = min(y1, height)
            r = g = b = a = 0
            n = 0
            for y in range(y0, y1, 2):
                row = y * width * 4
                for x in range(x0, x1, 2):
                    i = row + x * 4
                    al = px[i + 3]
                    r += px[i] * al
                    g += px[i + 1] * al
                    b += px[i + 2] * al
                    a += al
                    n += 1
            if a:
                print("  %-10s rgba(%3d,%3d,%3d,%3d) avg_alpha=%3d" % (
                    name, r // a, g // a, b // a, a // n, a // n))
            else:
                print("  %-10s fully transparent" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
