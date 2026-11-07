#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report the opaque bounding box of a PNG using only stdlib."""
from __future__ import print_function

import struct
import sys
import zlib


def load_rgba(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == "\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = depth = color = None
    idat = []
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == "IHDR":
            width, height, depth, color = struct.unpack(">IIBB", body[:10])
        elif kind == "IDAT":
            idat.append(body)
        elif kind == "IEND":
            break
    if depth != 8 or color != 6:
        raise SystemExit("unsupported png depth=%s color=%s" % (depth, color))
    raw = zlib.decompress("".join(idat))
    stride = width * 4
    out = bytearray(stride * height)
    prev = bytearray(stride)
    i = 0
    for y in range(height):
        filt = ord(raw[i])
        i += 1
        line = bytearray(raw[i:i + stride])
        i += stride
        if filt == 1:
            for x in range(4, stride):
                line[x] = (line[x] + line[x - 4]) & 0xFF
        elif filt == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif filt == 3:
            for x in range(stride):
                left = line[x - 4] if x >= 4 else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif filt == 4:
            for x in range(stride):
                a = line[x - 4] if x >= 4 else 0
                b = prev[x]
                c = prev[x - 4] if x >= 4 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return width, height, out


def main():
    for path in sys.argv[1:]:
        width, height, px = load_rgba(path)
        minx, miny, maxx, maxy = width, height, -1, -1
        for y in range(height):
            row = y * width * 4
            for x in range(width):
                if px[row + x * 4 + 3]:
                    if x < minx:
                        minx = x
                    if x > maxx:
                        maxx = x
                    if y < miny:
                        miny = y
                    if y > maxy:
                        maxy = y
        print("%s size=%dx%d bbox=(%d,%d)-(%d,%d)" % (path.split("\\")[-1], width, height, minx, miny, maxx, maxy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
