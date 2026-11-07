#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate dialogue/voice coverage and ending metadata in script.json."""
from __future__ import print_function

import collections
import io
import json


def find_unreachable(ops, labels, start):
    """Labels control flow can never reach from the start label."""
    total = len(ops)

    def targets(index):
        op = ops[index]
        kind = op[0]
        if kind == "jump":
            target = labels.get(op[1])
            return [target] if target is not None else []
        if kind == "call":
            target = labels.get(op[1])
            return [index + 1, target] if target is not None else [index + 1]
        if kind == "jump_abs":
            return [op[1]] if 0 <= op[1] < total else []
        if kind == "menu":
            return [c[2] for c in op[1] if 0 <= c[2] < total] + [index + 1]
        if kind == "if":
            return [e[1] for e in op[1] if 0 <= e[1] < total] + [index + 1]
        return [index + 1]

    seen = set()
    stack = [labels[start]]
    while stack:
        index = stack.pop()
        if index in seen or index < 0 or index >= total:
            continue
        seen.add(index)
        for target in targets(index):
            if target not in seen:
                stack.append(target)
    return sorted(
        name for name, index in labels.items() if index not in seen and name != "splashscreen"
    )


def main():
    data = json.load(io.open("build/script.json", encoding="utf-8"))
    ops = data["ops"]
    labels = data["labels"]
    ordered = sorted(labels.items(), key=lambda kv: kv[1])
    bounds = []
    for i, (name, idx) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(ops)
        bounds.append((name, idx, end))

    no_voice = collections.Counter()
    empty_voice = 0
    bad_wait = 0
    for name, start, end in bounds:
        has_voice_op = False
        for i in range(start, end):
            op = ops[i]
            if op[0] == "voice":
                has_voice_op = True
            elif op[0] == "say":
                if not op[5]:
                    empty_voice += 1
                    no_voice[name] += 1
                if op[3] < 0 or op[4] < 0:
                    bad_wait += 1
        if any(ops[i][0] == "say" for i in range(start, end)) and not has_voice_op:
            print("label without voice op:", name)
    print("says with empty voice:", empty_voice, dict(no_voice))
    print("says with missing wait:", bad_wait)

    unreachable = find_unreachable(ops, labels, data.get("start"))
    print("unreachable story labels:", len(unreachable), unreachable)
    status = 1 if unreachable else 0

    endings = data["endings"]
    print("endings:", len(endings))
    for e in endings:
        text = e.get("text") or ""
        print("  %s %-42s text=%d" % (e.get("id"), (e.get("title") or "")[:42], len(text)))
    print("gui keys:", sorted((data.get("gui") or {}).keys()))
    print("labels with no say:", sum(1 for n, s, e in bounds if not any(ops[i][0] == "say" for i in range(s, e))))
    return status


if __name__ == "__main__":
    main()
