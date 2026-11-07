#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inspect the PyCode payload stored in Ren'Py Python AST nodes."""
from __future__ import print_function

import marshal
import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import export_script as ex


def main():
    path = os.path.abspath(sys.argv[1])
    label = sys.argv[2]
    data, stmts = ex.read_rpyc(path)

    def visit(node):
        if ex.tname(node) != "Python":
            return
        code = getattr(node, "code", None)
        if code is None:
            return
        print("PyCode attrs:", [a for a in dir(code) if not a.startswith("__")])
        for name in ("source", "mode", "bytecode", "location", "_pickle_state"):
            value = getattr(code, name, None)
            if isinstance(value, str):
                print("  %s len=%d prefix=%r" % (name, len(value), value[:200]))
            else:
                print("  %s = %r" % (name, value))
        bc = getattr(code, "bytecode", None)
        if isinstance(bc, str):
            try:
                obj = marshal.loads(bc)
                print("  marshalled:", type(obj), obj)
                if isinstance(obj, types.CodeType):
                    print("  consts:", obj.co_consts)
                    print("  names:", obj.co_names)
                    print("  varnames:", obj.co_varnames)
            except Exception as err:
                print("  marshal failed:", err)
        raise SystemExit

    def find(node):
        pass

    for node in stmts:
        if getattr(node, "name", None) == label:
            ex.walk_nodes(node.block, visit)
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
