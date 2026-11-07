#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Text preview of the linear bytecode produced for the PS5 runtime.

This is a small companion interpreter for build/script.json.  It follows the
same control flow as src/engine.c (say / menu / scene / show / play / ending)
but renders no graphics, so script coverage can be checked without a GPU.

Examples:
    python tools/host_preview.py --auto --max 300
    python tools/host_preview.py --from-label start
    python tools/host_preview.py --choice 2

Notes:
  * --auto       never prompts; menus pick --choice (default 1)
  * --max N      stop after N executed ops (0 = unlimited)
  * --splash     begin at op 0 (splashscreen) instead of the "start" label
  * --verbose    also print staging / audio / control-flow ops
"""
from __future__ import print_function

import argparse
import io
import json
import os
import sys

try:
    input = raw_input
except NameError:
    pass


def write_line(text):
    """Print unicode without blowing up on a legacy Windows console."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


class Runtime(object):
    def __init__(self, data, options):
        self.data = data
        self.ops = data.get("ops") or []
        self.labels = data.get("labels") or {}
        self.endings = {}
        for ending in data.get("endings") or []:
            self.endings[ending.get("id")] = ending
        self.options = options
        self.seen = set()
        self.call_stack = []
        self.pc = 0
        self.items = []          # dicts mirroring LayerItem
        self.audio = {}
        self.voice = ""
        self.hud = 1
        self.choice_count = 0
        self.executed = 0
        self.ending_done = False
        if options.splash:
            self.pc = 0
        else:
            self.pc = self.labels.get(data.get("start"), 0)

    # -- helpers ------------------------------------------------------------
    def verbose(self, text):
        if self.options.verbose:
            write_line("    [%s]" % text)

    def jump_label(self, name):
        if name in self.labels:
            self.pc = self.labels[name]
            return True
        write_line("[missing label: %s]" % name)
        self.pc += 1
        return False

    def ending_is_seen(self, ending_id):
        return ending_id in self.seen

    def eval_cond(self, expr):
        """Match eval_cond() in engine.c (only ending_seen expressions occur)."""
        if expr in (None, "", "True", "true"):
            return True
        if expr in ("False", "false"):
            return False
        ending_id = None
        for i in range(0, max(0, len(expr) - 3)):
            chunk = expr[i:i + 4]
            if chunk.isdigit():
                ending_id = chunk
                break
        if ending_id is None:
            return True
        seen = self.ending_is_seen(ending_id)
        if "not in" in expr:
            return not seen
        return seen

    def find_item(self, tag, layer):
        for item in self.items:
            if item["tag"] == tag and item["layer"] == layer:
                return item
        return None

    def set_item(self, rel, tag, layer, kind, arg, x, y, w, h, alpha, flip):
        item = self.find_item(tag, layer)
        if item is None:
            item = {"tag": tag, "layer": layer or "master"}
            self.items.append(item)
        item.update({
            "rel": rel or "",
            "kind": kind or "none",
            "arg": arg or "",
            "x": x, "y": y, "w": w, "h": h,
            "alpha": alpha, "flip": flip,
        })

    def clear_layer(self, layer):
        self.items = [item for item in self.items if item["layer"] != layer]

    def describe_items(self):
        master = [item for item in self.items if item["layer"] == "master"]
        screens = [item for item in self.items if item["layer"] == "screens"]
        if master:
            names = ", ".join(item["tag"] for item in master)
            write_line("  scene: %s" % names)
        if screens:
            names = ", ".join(item["tag"] for item in screens)
            write_line("  overlay: %s" % names)

    def wait_for_player(self, prompt):
        if self.options.auto:
            return
        try:
            input(prompt)
        except EOFError:
            self.options.auto = True

    # -- interpreter --------------------------------------------------------
    def step(self):
        if self.pc < 0 or self.pc >= len(self.ops):
            return False
        if self.options.max > 0 and self.executed >= self.options.max:
            write_line("[stopped after %d ops]" % self.executed)
            return False
        op = self.ops[self.pc]
        kind = op[0] if op else ""
        self.executed += 1

        if kind == "label":
            self.verbose("label %s" % (op[1] if len(op) > 1 else ""))
            self.pc += 1
            return True

        if kind == "say":
            who = op[1] if len(op) > 1 else ""
            what = op[2] if len(op) > 2 else ""
            start = float(op[3]) if len(op) > 3 else 0.0
            end = float(op[4]) if len(op) > 4 else 0.0
            voice = op[5] if len(op) > 5 else ""
            self.voice = voice or self.voice
            write_line("")
            self.describe_items()
            write_line("%s: %s" % (who or "...", what))
            if voice and self.options.verbose:
                write_line("  voice: %s (%.2f..%.2f)" % (voice, start, end))
            self.wait_for_player("  [Cross / Enter] ")
            self.pc += 1
            return True

        if kind == "voice":
            self.voice = op[1] if len(op) > 1 else ""
            self.verbose("voice %s" % self.voice)
            self.pc += 1
            return True

        if kind == "scene":
            rel = op[1] if len(op) > 1 else ""
            scene_kind = op[2] if len(op) > 2 else "image"
            arg = op[3] if len(op) > 3 else ""
            self.clear_layer("master")
            if scene_kind and scene_kind != "none":
                self.set_item(rel, "_scene", "master", scene_kind, arg,
                              self.int_at(op, 4), self.int_at(op, 5),
                              self.int_at(op, 6), self.int_at(op, 7),
                              self.int_at(op, 8), self.int_at(op, 9))
            self.verbose("scene %s (%s)" % (rel, scene_kind))
            self.pc += 1
            return True

        if kind == "show":
            layer = op[3] if len(op) > 3 else "master"
            self.set_item(op[1] if len(op) > 1 else "",
                          op[2] if len(op) > 2 else "",
                          layer,
                          op[4] if len(op) > 4 else "image",
                          op[5] if len(op) > 5 else "",
                          self.int_at(op, 6), self.int_at(op, 7),
                          self.int_at(op, 8), self.int_at(op, 9),
                          self.int_at(op, 10), self.int_at(op, 11))
            self.verbose("show %s/%s on %s" % (op[2] if len(op) > 2 else "", op[1] if len(op) > 1 else "", layer))
            self.pc += 1
            return True

        if kind == "hide":
            tag = op[1] if len(op) > 1 else ""
            layer = op[2] if len(op) > 2 else ""
            self.items = [item for item in self.items
                          if not ((not tag or item["tag"] == tag) and
                                  (not layer or item["layer"] == layer))]
            self.verbose("hide %s/%s" % (tag, layer))
            self.pc += 1
            return True

        if kind == "play":
            channel = op[1] if len(op) > 1 else "music"
            self.audio[channel] = op[2] if len(op) > 2 else ""
            self.verbose("play %s %s" % (channel, self.audio[channel]))
            self.pc += 1
            return True

        if kind == "stop":
            channel = op[1] if len(op) > 1 else "music"
            self.audio.pop(channel, None)
            self.verbose("stop %s" % channel)
            self.pc += 1
            return True

        if kind == "pause":
            seconds = float(op[1]) if len(op) > 1 else 0.0
            self.verbose("pause %.2fs" % seconds)
            self.pc += 1
            return True

        if kind == "movie":
            rel = op[1] if len(op) > 1 else ""
            write_line("  [movie skipped: %s]" % rel)
            self.pc += 1
            return True

        if kind == "jump":
            return self.jump_label(op[1] if len(op) > 1 else "")

        if kind == "jump_abs":
            self.pc = self.int_at(op, 1)
            return True

        if kind == "call":
            self.call_stack.append(self.pc + 1)
            return self.jump_label(op[1] if len(op) > 1 else "")

        if kind == "return":
            if self.call_stack:
                self.pc = self.call_stack.pop()
            else:
                write_line("")
                write_line("[top-level return: runtime shows the main menu]")
                return False
            return True

        if kind == "menu":
            return self.do_menu(op)

        if kind == "if":
            for entry in op[1] or []:
                if len(entry) >= 2 and self.eval_cond(entry[0]):
                    self.pc = entry[1]
                    return True
            self.pc += 1
            return True

        if kind == "hud":
            self.hud = self.int_at(op, 1)
            self.verbose("hud %d" % self.hud)
            self.pc += 1
            return True

        if kind == "ending_seen":
            ending_id = op[1] if len(op) > 1 else ""
            self.seen.add(ending_id)
            self.verbose("ending_seen %s" % ending_id)
            self.pc += 1
            return True

        if kind == "ending":
            return self.do_ending(op)

        write_line("[unknown op: %s]" % (op,))
        self.pc += 1
        return True

    def do_menu(self, op):
        choices = op[1] if len(op) > 1 else []
        visible = []
        write_line("")
        for choice in choices:
            if len(choice) < 3:
                continue
            text, cond, target = choice[0], choice[1], choice[2]
            if self.eval_cond(cond):
                visible.append((text, target))
                write_line("  %d) %s" % (len(visible), text))
        self.choice_count = len(visible)
        if not visible:
            self.pc += 1
            return True
        if self.options.auto:
            index = max(0, min(self.options.choice - 1, len(visible) - 1))
        else:
            raw = ""
            try:
                raw = input("  [D-pad + Cross] choice: ").strip()
            except EOFError:
                self.options.auto = True
            try:
                index = int(raw) - 1
            except Exception:
                index = max(0, min(self.options.choice - 1, len(visible) - 1))
            index = max(0, min(index, len(visible) - 1))
        write_line("  -> %s" % visible[index][0])
        self.pc = visible[index][1]
        return True

    def do_ending(self, op):
        ending_id = op[1] if len(op) > 1 else ""
        info = self.endings.get(ending_id) or {}
        title = info.get("title") or "Ending"
        body = info.get("text") or ""
        write_line("")
        write_line("=" * 68)
        write_line("ENDING %s - %s" % (ending_id, title))
        write_line("=" * 68)
        if body:
            write_line(body)
        self.ending_done = True
        self.seen.add(ending_id)
        self.wait_for_player("  [Cross / Enter] ")
        self.pc += 1
        return True

    @staticmethod
    def int_at(op, index):
        try:
            return int(op[index])
        except Exception:
            return 0


def load_script(path):
    with io.open(path, "r", encoding="utf-8") as handle:
        return json.loads(handle.read())


def parse_args(argv):
    here = os.path.abspath(os.path.dirname(__file__))
    project = os.path.abspath(os.path.join(here, os.pardir))
    default_script = os.path.join(project, "build", "script.json")
    parser = argparse.ArgumentParser(description="Text preview of the exported Class of '09 bytecode.")
    parser.add_argument("script", nargs="?", default=default_script, help="path to script.json")
    parser.add_argument("--auto", action="store_true", help="advance without prompting")
    parser.add_argument("--max", type=int, default=0, help="stop after N ops (0 = unlimited)")
    parser.add_argument("--choice", type=int, default=1, help="1-based menu choice used by --auto")
    parser.add_argument("--from-label", default="", help="start at this label instead of the script's start label")
    parser.add_argument("--splash", action="store_true", help="start at op 0 (splashscreen) instead of the start label")
    parser.add_argument("--verbose", action="store_true", help="also print staging and control-flow ops")
    return parser.parse_args(argv)


def main(argv=None):
    options = parse_args(argv if argv is not None else sys.argv[1:])
    script_path = os.path.abspath(options.script)
    if not os.path.isfile(script_path):
        write_line("Missing %s" % script_path)
        write_line("Run tools/export_script.py first.")
        return 1
    data = load_script(script_path)
    ops = data.get("ops") or []
    labels = data.get("labels") or {}
    write_line("Class of '09 PS5 runtime preview")
    write_line("ops=%d labels=%d endings=%d" % (len(ops), len(labels), len(data.get("endings") or [])))
    if options.from_label:
        if options.from_label not in labels:
            write_line("Unknown label: %s" % options.from_label)
            return 1
        options.splash = False
    runtime = Runtime(data, options)
    if options.from_label:
        runtime.pc = labels[options.from_label]
    write_line("Cross/Enter advances. Ctrl+C quits.")
    if options.auto:
        write_line("Auto mode: menus pick choice %d." % options.choice)
    try:
        while runtime.step():
            pass
    except KeyboardInterrupt:
        write_line("")
        write_line("Stopped at pc %d after %d ops" % (runtime.pc, runtime.executed))
        return 0
    write_line("")
    write_line("Playback finished at pc %d after %d ops" % (runtime.pc, runtime.executed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
