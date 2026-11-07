#!/usr/bin/env python3
"""Report unreachable labels and branch menus in a format-v2 script.json."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "build/script.json"
data = json.load(open(path, encoding="utf-8"))
ops = data["ops"]
labels = data["labels"]
n = len(ops)


def successors(i):
    op = ops[i]
    kind = op[0]
    if kind == "jump":
        target = labels.get(op[1])
        return [target] if target is not None else []
    if kind == "call":
        target = labels.get(op[1])
        return [i + 1, target] if target is not None else [i + 1]
    if kind == "jump_abs":
        return [op[1]] if 0 <= op[1] < n else []
    if kind == "menu":
        return [c[2] for c in op[1] if 0 <= c[2] < n] + [i + 1]
    if kind == "if":
        return [e[1] for e in op[1] if 0 <= e[1] < n] + [i + 1]
    if kind in ("return",):
        return [i + 1]
    return [i + 1]


seen = set()
stack = [labels[data["start"]]]
while stack:
    i = stack.pop()
    if i in seen or i < 0 or i >= n:
        continue
    seen.add(i)
    for j in successors(i):
        if j not in seen:
            stack.append(j)

unreachable = sorted(
    ((idx, name) for name, idx in labels.items() if idx not in seen and name != "splashscreen"),
    key=lambda item: item[0],
)
print("unreachable story labels:", len(unreachable))
for idx, name in unreachable:
    print("  %5d %s" % (idx, name))

menus = [(i, op) for i, op in enumerate(ops) if op[0] == "menu"]
print("menus:", len(menus))
for i, op in menus:
    print("  %5d %s" % (i, [c[0] for c in op[1]]))
