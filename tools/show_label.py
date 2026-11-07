#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print the ops for one label in build/script.json."""
from __future__ import print_function

import io
import json
import sys


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "end_0039"
    before = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    data = json.load(io.open("build/script.json", encoding="utf-8"))
    ops = data["ops"]
    idx = data["labels"][name]
    start = max(0, idx - before)
    for i in range(start, min(len(ops), start + count)):
        print("%5d  %s" % (i, ops[i]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
