#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Decompile Class of '09 .rpyc files into linear bytecode JSON (format v2).

Run with the game's bundled Python 2.7 so the pickle layout matches Ren'Py 7.5.

The exporter does not copy any game assets.  It resolves image/audio names to
the relative paths that exist in your own game/ folder, evaluates the inline
ATL blocks that Ren'Py uses for character staging, and turns the game's
speak()/setWait()/setVoiceTrack() Python calls into structured dialogue ops.
"""
from __future__ import print_function

import ast
import collections
import difflib
import io
import itertools
import json
import os
import re
import struct
import sys
import zlib

import pickle


RPYC2_HEADER = b"RENPY RPC2"
FAKES = {}

SCREEN_W = 1920
SCREEN_H = 1080

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
AUDIO_EXTS = (".mp3", ".ogg", ".wav")
VIDEO_EXTS = (".webm", ".mp4")

SOLID_RE = re.compile(r"Solid\s*\(\s*\(([^)]*)\)")
MOVIE_RE = re.compile(r"Movie\s*\(\s*play\s*=\s*[\"']([^\"']+)[\"']")
FLIP_RE = re.compile(r"im\.Flip\s*\(\s*[\"']([^\"']+)[\"']")
IMAGE_RE = re.compile(r"^\s*Image\s*\(\s*[\"']([^\"']+)[\"']")
CHARACTER_RE = re.compile(r"Character\s*\(\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')")
ENDING_APPEND_RE = re.compile(r"persistent\.endings\.append\s*\(\s*[\"']end_(\d{4})[\"']")
ENDING_MAP_RE = re.compile(r"[\"'](\d{4})[\"']\s*:\s*[\"']([^\"']+)[\"']")
QUICK_MENU_RE = re.compile(r"^\s*quick_menu\s*=\s*(True|False)\s*$", re.M)
PAUSE_RE = re.compile(r"renpy\.pause\s*\(\s*([0-9.]+)")
WITH_PAUSE_RE = re.compile(r"Pause\s*\(\s*([0-9.]+)\s*\)")
PLAY_RE = re.compile(r"^\s*play\s+(\w+)\s+[\"']([^\"']+)[\"'](.*)$")
STOP_RE = re.compile(r"^\s*stop\s+(\w+)(.*)$")
FADE_RE = re.compile(r"fade(?:in|out)\s+([0-9.]+)")


class Fake(object):
    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)
        elif isinstance(state, tuple) and len(state) == 2:
            dct, slots = state
            if dct:
                self.__dict__.update(dct)
            if slots:
                self.__dict__.update(slots)
        else:
            self._pickle_state = state

    def __repr__(self):
        return "<%s>" % self.__class__.__name__


def make_fake(module, name):
    key = module + "." + name
    existing = FAKES.get(key)
    if existing is not None:
        return existing
    cls = type(str(name), (Fake,), {"__module__": str(module)})
    FAKES[key] = cls
    return cls


class PyExprStr(str):
    """String subclass standing in for renpy.ast.PyExpr."""

    def __new__(cls, *args):
        self = str.__new__(cls, args[0] if args else "")
        self.filename = args[1] if len(args) > 1 else None
        self.linenumber = args[2] if len(args) > 2 else None
        self.py = args[3] if len(args) > 3 else 2
        return self


class PyCodeObj(object):
    """Minimal stand-in for renpy.ast.PyCode."""

    def __setstate__(self, state):
        self.source, self.location, self.mode, self.py = None, None, "exec", 2
        self.bytecode = None
        if state:
            if len(state) >= 4:
                _, self.source, self.location, self.mode = state[:4]
                self.py = state[4] if len(state) > 4 else 2
            else:
                self._pickle_state = state


class RelaxedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module in ("__builtin__", "builtins"):
            return pickle.Unpickler.find_class(self, module, name)
        if module == "renpy.ast" and name == "PyExpr":
            return PyExprStr
        if module == "renpy.ast" and name == "PyCode":
            return PyCodeObj
        if name in ("RevertableDict", "DefaultDict"):
            return dict
        if name in ("RevertableList",):
            return list
        if name in ("RevertableSet",):
            return set
        if name in ("RevertableObject",):
            return Fake
        if module.startswith("renpy") or module.startswith("store") or module == "copy_reg":
            if module == "copy_reg" and name == "_reconstructor":
                return pickle.Unpickler.find_class(self, module, name)
            return make_fake(module, name)
        try:
            return pickle.Unpickler.find_class(self, module, name)
        except Exception:
            return make_fake(module, name)


def read_rpyc(path):
    with open(path, "rb") as f:
        header = f.read(1024)
        if header[: len(RPYC2_HEADER)] != RPYC2_HEADER:
            f.seek(0)
            return pickle_loads(zlib.decompress(f.read()))

        pos = len(RPYC2_HEADER)
        slots = {}
        while True:
            slot, start, length = struct.unpack("III", header[pos : pos + 12])
            if slot == 0:
                break
            slots[slot] = (start, length)
            pos += 12

        last_error = None
        for slot in (2, 1):
            if slot not in slots:
                continue
            start, length = slots[slot]
            f.seek(start)
            try:
                return pickle_loads(zlib.decompress(f.read(length)))
            except Exception as err:
                last_error = err
                continue
        raise RuntimeError("Could not unpickle %s: %s" % (path, last_error))


def pickle_loads(blob):
    return RelaxedUnpickler(io.BytesIO(blob)).load()


def tname(obj):
    return obj.__class__.__name__


def as_text(value):
    if value is None:
        return None
    if isinstance(value, unicode):
        return value
    if isinstance(value, str):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("latin-1", "replace")
    if isinstance(value, (list, tuple)):
        return " ".join(as_text(part) for part in value if part is not None)
    return unicode(value)


def py_source(node):
    code = getattr(node, "code", None)
    if code is None:
        return None
    src = getattr(code, "source", None)
    if src is None:
        src = getattr(code, "bytecode", None)
    return as_text(src) if src is not None else None


def walk_nodes(nodes, visitor):
    if not nodes:
        return
    for node in nodes:
        visitor(node)
        block = getattr(node, "block", None)
        if block:
            walk_nodes(block, visitor)
        entries = getattr(node, "entries", None)
        if entries:
            for item in entries:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    walk_nodes(item[-1], visitor)
        items = getattr(node, "items", None)
        if items:
            for item in items:
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    walk_nodes(item[2], visitor)
        code_block = getattr(node, "code_block", None)
        if code_block:
            walk_nodes(code_block, visitor)


# ---------------------------------------------------------------------------
# image helpers
# ---------------------------------------------------------------------------


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
    while i + 4 < len(data):
        if data[i] != "\xff":
            i += 1
            continue
        marker = ord(data[i + 1])
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        if marker in (0xD8, 0xD9):
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        i += 2 + length
    return None


def size_of(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".png":
            return png_size(path)
        if ext in (".jpg", ".jpeg"):
            return jpg_size(path)
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# ATL / staging
# ---------------------------------------------------------------------------

PREDEFINED = {
    "left": {"xpos": 0.0, "xanchor": 0.0, "ypos": 1.0, "yanchor": 1.0},
    "right": {"xpos": 1.0, "xanchor": 1.0, "ypos": 1.0, "yanchor": 1.0},
    "center": {"xpos": 0.5, "xanchor": 0.5, "ypos": 1.0, "yanchor": 1.0},
    "truecenter": {"xpos": 0.5, "xanchor": 0.5, "ypos": 0.5, "yanchor": 0.5},
    "topleft": {"xpos": 0.0, "xanchor": 0.0, "ypos": 0.0, "yanchor": 0.0},
    "topright": {"xpos": 1.0, "xanchor": 1.0, "ypos": 0.0, "yanchor": 0.0},
    "top": {"xpos": 0.5, "xanchor": 0.5, "ypos": 0.0, "yanchor": 0.0},
    "offscreenleft": {"xpos": 0.0, "xanchor": 1.0, "ypos": 1.0, "yanchor": 1.0},
    "offscreenright": {"xpos": 1.0, "xanchor": 0.0, "ypos": 1.0, "yanchor": 1.0},
}


def new_state():
    return {
        "xpos": 0.5,
        "xanchor": 0.5,
        "ypos": 1.0,
        "yanchor": 1.0,
        "zoom": 1.0,
        "xzoom": 1.0,
        "yzoom": 1.0,
        "alpha": 1.0,
        "flip": 0,
    }


def to_float(value):
    try:
        return float(as_text(value))
    except Exception:
        return None


def apply_props(state, props):
    if not props:
        return
    if isinstance(props, dict):
        items = props.items()
    else:
        items = props
    for key, value in items:
        key = as_text(key)
        num = to_float(value)
        if num is None:
            continue
        if key == "xalign":
            state["xpos"] = num
            state["xanchor"] = num
        elif key == "xcenter":
            state["xpos"] = num
            state["xanchor"] = 0.5
        elif key == "yalign":
            state["ypos"] = num
            state["yanchor"] = num
        elif key == "ycenter":
            state["ypos"] = num
            state["yanchor"] = 0.5
        elif key == "xpos":
            state["xpos"] = num
        elif key == "xanchor":
            state["xanchor"] = num
        elif key == "ypos":
            state["ypos"] = num
        elif key == "yanchor":
            state["yanchor"] = num
        elif key == "zoom":
            state["zoom"] = num
        elif key == "xzoom":
            state["xzoom"] = num
            state["flip"] = 1 if num < 0 else 0
        elif key == "yzoom":
            state["yzoom"] = num
        elif key == "alpha":
            if num < 0.0:
                num = 0.0
            if num > 1.0:
                num = 1.0
            state["alpha"] = num


def iter_atl_statements(block):
    for st in getattr(block, "statements", None) or []:
        if type(st).__name__ == "RawParallel":
            for child in getattr(st, "blocks", None) or []:
                for item in iter_atl_statements(child):
                    yield item
        else:
            yield st


def sample_tracks(base, tracks, when):
    """Sample every animated property at one point in time."""
    state = dict(base)
    for t0, t1, key, v0, v1, _warper in tracks:
        if t1 <= t0:
            value = v1 if when >= t1 else v0
        elif when >= t1:
            value = v1
        elif when <= t0:
            value = v0
        else:
            ratio = (when - t0) / (t1 - t0)
            value = v0 + (v1 - v0) * ratio
        state[key] = value
    return state


def eval_atl_timeline(block, transforms, clock=0.0, state=None):
    """Turn an ATL block into property tracks.

    Ren'Py ATL is a sequence of statements.  A statement with a duration
    interpolates towards its new properties; a bare number is a pause; and
    parallel blocks animate independently.  Each track records the start and
    end time for one property so the runtime can reproduce the motion instead
    of jumping straight to the final staging.
    """
    if state is None:
        state = new_state()
    tracks = []
    if block is None:
        return clock, state, tracks

    for st in getattr(block, "statements", None) or []:
        if type(st).__name__ == "RawParallel":
            start = clock
            base = dict(state)
            children = []
            for child in getattr(st, "blocks", None) or []:
                children.append(eval_atl_timeline(child, transforms, start, dict(base)))
            end = start
            child_tracks = []
            for child_end, _child_state, child_track_list in children:
                end = max(end, child_end)
                child_tracks.extend(child_track_list)
            state = sample_tracks(base, child_tracks, end)
            tracks.extend(child_tracks)
            clock = end
            continue

        duration = to_float(getattr(st, "duration", None))
        if duration is None or duration < 0.0:
            duration = 0.0
        warper = as_text(getattr(st, "warper", None)) or "linear"

        target = dict(state)
        changed = False
        pause_extra = 0.0

        props = getattr(st, "properties", None)
        if props:
            apply_props(target, props)
            changed = True

        for expr in getattr(st, "expressions", None) or []:
            text = as_text(expr[0] if isinstance(expr, (list, tuple)) else expr)
            if not text:
                continue
            if "im.Flip" in text:
                if target.get("flip") != 1:
                    target["flip"] = 1
                    changed = True
                continue
            if text in transforms:
                apply_props(target, transforms[text])
                changed = True
                continue
            if text in PREDEFINED:
                apply_props(target, PREDEFINED[text])
                changed = True
                continue
            pause = to_float(text)
            if pause is not None and pause > 0.0:
                pause_extra += pause

        if not changed:
            if duration > 0.0:
                clock += duration
            elif pause_extra > 0.0:
                clock += pause_extra
            continue

        # A timed transform/property line interpolates from the current state;
        # a zero-duration line (e.g. `off_left` or `xzoom -1`) applies at once.
        for key in state:
            if target[key] == state[key]:
                continue
            if key == "flip" or duration <= 0.0:
                tracks.append((clock + duration, clock + duration, key, state[key], target[key], warper))
            else:
                tracks.append((clock, clock + duration, key, state[key], target[key], warper))
        state = target
        clock += duration
        if duration <= 0.0 and pause_extra > 0.0:
            clock += pause_extra

    return clock, state, tracks


def state_geometry(state, w0, h0):
    sx = state["zoom"] * abs(state["xzoom"])
    sy = state["zoom"] * abs(state["yzoom"])
    w = max(1, int(round(w0 * sx)))
    h = max(1, int(round(h0 * sy)))
    x = int(round(state["xpos"] * SCREEN_W - state["xanchor"] * w))
    y = int(round(state["ypos"] * SCREEN_H - state["yanchor"] * h))
    return x, y, w, h


def build_animation(w0, h0, base, tracks):
    """Build compact keyframes from the per-property tracks."""
    if not tracks:
        return None
    times = set([0.0])
    for t0, t1, _key, _v0, _v1, _warper in tracks:
        times.add(t0)
        times.add(t1)
    frames = []
    for when in sorted(times):
        state = sample_tracks(base, tracks, when)
        x, y, w, h = state_geometry(state, w0, h0)
        alpha = int(round(state["alpha"] * 255.0))
        flip = 1 if state["flip"] else 0
        frames.append([int(round(when * 1000.0)), x, y, w, h, alpha, flip])
    if len(frames) < 2:
        return None
    if all(frame[1:] == frames[0][1:] for frame in frames):
        return None
    return frames


# ---------------------------------------------------------------------------
# assembler
# ---------------------------------------------------------------------------


class Assembler(object):
    def __init__(self, game_dir, files, index, image_defs, transforms, characters, endings):
        self.game_dir = game_dir
        self.files = files
        self.index = index
        self.image_defs = image_defs
        self.transforms = transforms
        self.characters = characters
        self.endings = endings
        self.word_index = self.build_word_index()

        self.ops = []
        self.labels = {}
        self.stats = collections.Counter()
        self.unsupported = collections.Counter()
        self.unresolved_images = collections.Counter()
        self.unresolved_audio = collections.Counter()
        self.size_cache = {}
        # Current transform state per (layer, tag).  Ren'Py keeps a tag's
        # transform when a later `show` has no `at`/ATL block; the exporter
        # needs that state to avoid snapping the character back to center.
        self.tag_state = {}

        self.voice = ""
        self.wait_start = -1.0
        self.wait_end = -1.0
        self.skip_next_pause = False

    # -- helpers ---------------------------------------------------------

    def build_word_index(self):
        result = {}
        prefix = "images/"
        for rel in self.files:
            low = rel.lower()
            if not low.startswith(prefix):
                continue
            ext = os.path.splitext(low)[1]
            if ext not in IMAGE_EXTS:
                continue
            stem = os.path.splitext(os.path.basename(rel))[0]
            key = tuple(sorted(stem.lower().split()))
            if key not in result:
                result[key] = rel
        return result

    def emit(self, op):
        self.ops.append(op)
        return len(self.ops) - 1

    def patch(self, index, op):
        self.ops[index] = op

    def locate(self, rel):
        if not rel:
            return None
        return self.index.get(rel.replace("\\", "/").lower())

    def locate_image(self, name):
        if not name:
            return None
        name = name.strip().replace("\\", "/")
        has_ext = os.path.splitext(name)[1].lower() in IMAGE_EXTS
        candidates = []
        if has_ext:
            candidates.append("images/" + name)
            candidates.append(name)
        else:
            for ext in IMAGE_EXTS:
                candidates.append("images/" + name + ext)
            for ext in IMAGE_EXTS:
                candidates.append(name + ext)
        for cand in candidates:
            found = self.locate(cand)
            if found:
                return found

        words = name.split()
        if len(words) > 1 and len(words) <= 6:
            for perm in itertools.permutations(words):
                joined = " ".join(perm)
                for ext in IMAGE_EXTS:
                    found = self.locate("images/" + joined + ext)
                    if found:
                        return found

        stem = os.path.splitext(name)[0]
        key = tuple(sorted(stem.lower().split()))
        return self.word_index.get(key)

    def locate_audio(self, name):
        if not name:
            return None
        name = name.strip().replace("\\", "/")
        found = self.locate(name)
        if found:
            return found
        found = self.locate("audio/" + name)
        return found

    def locate_video(self, name):
        if not name:
            return None
        name = name.strip().replace("\\", "/")
        return self.locate(name) or self.locate("images/" + name)

    def image_size(self, rel):
        if not rel:
            return (SCREEN_W, SCREEN_H)
        if rel in self.size_cache:
            return self.size_cache[rel]
        dim = size_of(os.path.join(self.game_dir, rel))
        if not dim:
            dim = (SCREEN_W, SCREEN_H)
        self.size_cache[rel] = dim
        return dim

    def base_size(self, kind, rel):
        if kind in ("solid", "movie"):
            return SCREEN_W, SCREEN_H
        return self.image_size(rel)

    def place(self, kind, rel, atl, layer="master", base=None):
        w0, h0 = self.base_size(kind, rel)
        start = dict(base) if base is not None else None
        _end, state, tracks = eval_atl_timeline(atl, self.transforms, state=start)
        sample_base = dict(base) if base is not None else new_state()
        frames = build_animation(w0, h0, sample_base, tracks)
        x, y, w, h = state_geometry(state, w0, h0)
        return x, y, w, h, round(state["alpha"], 3), int(state["flip"]), frames, state

    def resolve_item(self, parts):
        """Return (kind, file, arg, forced_flip, resolved)."""
        label = " ".join(parts)
        source = self.image_defs.get(tuple(parts))
        flip = False

        # The Re-Up's looping smoke overlay: 120 numbered PNG frames.
        if label.strip().lower() == "smoke":
            return ("anim", "smokeloop/Comp 1_00001.png", "smoke", False, True)

        if source:
            match = MOVIE_RE.search(source)
            if match:
                rel = self.locate_video(match.group(1))
                return ("movie", "", rel or match.group(1), False, True)
            match = SOLID_RE.search(source)
            if match:
                return ("solid", "", match.group(1).strip(), False, True)
            match = FLIP_RE.search(source)
            if match:
                rel = self.locate_image(match.group(1))
                flip = True
                if rel:
                    return ("image", rel, "", flip, True)
                self.unresolved_images[label] += 1
                return ("none", "", "", flip, False)
            match = IMAGE_RE.search(source)
            if match:
                rel = self.locate_image(match.group(1))
                if rel:
                    return ("image", rel, "", False, True)

        rel = self.locate_image(label)
        if rel:
            return ("image", rel, "", flip, True)

        self.unresolved_images[label] += 1
        return ("none", "", "", flip, False)

    # -- control flow ----------------------------------------------------

    def assemble(self, top_nodes):
        for node in top_nodes:
            kind = tname(node)
            if kind in ("Init", "InitOffset"):
                continue
            if kind == "Label":
                self.emit_label(node)
            else:
                # Ren'Py stores a menu that follows a label's block as a
                # sibling top-level node, so compile every top-level node in
                # order.  Skipping these silently removed 5 branch menus.
                self.emit_node(node)
        return {
            "format": 2,
            "title": "Class of '09: The Re-Up",
            "start": "start" if "start" in self.labels else (next(iter(self.labels), None) if self.labels else None),
            "labels": self.labels,
            "ops": self.ops,
            "characters": self.characters,
            "endings": [self.endings[key] for key in sorted(self.endings.keys())],
            "stats": dict(self.stats),
            "unsupported": dict(self.unsupported),
        }

    def emit_label(self, node):
        name = as_text(getattr(node, "name", None))
        if not name:
            return
        self.labels[name] = len(self.ops)
        self.emit(["label", name])
        self.walk_block(getattr(node, "block", None))

    def walk_block(self, nodes):
        if not nodes:
            return
        for node in nodes:
            self.emit_node(node)

    def emit_node(self, node):
        kind = tname(node)
        self.stats[kind] += 1

        if kind == "Label":
            self.emit_label(node)
            return

        if kind in ("Say", "TranslateSay"):
            who = as_text(getattr(node, "who", None)) or ""
            what = as_text(getattr(node, "what", "")) or ""
            display = self.characters.get(who, who)
            self.emit(["say", display, what, -1.0, -1.0, self.voice])
            return

        if kind == "Scene":
            self.emit_scene(node)
            return

        if kind == "Show":
            self.emit_show(node)
            return

        if kind == "Hide":
            self.emit_hide(node)
            return

        if kind == "Jump":
            target = as_text(getattr(node, "target", None))
            if getattr(node, "expression", False):
                self.unsupported["jump-expression"] += 1
                self.emit(["nop"])
            else:
                self.emit(["jump", target or ""])
            return

        if kind == "Call":
            target = as_text(getattr(node, "label", None))
            if getattr(node, "expression", False):
                self.unsupported["call-expression"] += 1
                self.emit(["nop"])
            else:
                self.emit(["call", target or ""])
            return

        if kind == "Return":
            self.emit(["return"])
            return

        if kind == "Menu":
            self.emit_menu(node)
            return

        if kind == "If":
            self.emit_if(node)
            return

        if kind in ("Python", "EarlyPython"):
            self.handle_python(py_source(node))
            return

        if kind == "UserStatement":
            self.emit_user_statement(as_text(getattr(node, "line", "")) or "")
            self.walk_block(getattr(node, "code_block", None))
            return

        if kind in ("Translate", "TranslateBlock", "EndTranslate", "Init", "InitOffset"):
            self.walk_block(getattr(node, "block", None))
            return

        if kind == "With":
            self.emit_with(node)
            return

        if kind in ("Image", "Define", "Default", "Transform", "Style", "Screen", "Pass"):
            return

        self.unsupported[kind] += 1
        self.emit(["nop"])

    # -- image ops -------------------------------------------------------

    def emit_scene(self, node):
        spec = getattr(node, "imspec", None)
        if not spec or not spec[0]:
            self.emit(["scene", "", "none", "", 0, 0, 0, 0, 0, 0, None])
            self.tag_state = dict((k, v) for k, v in self.tag_state.items() if k[0] != "master")
            return
        parts = tuple(as_text(part) for part in spec[0])
        atl = getattr(node, "atl", None)
        kind, rel, arg, forced_flip, _ok = self.resolve_item(parts)
        if forced_flip:
            atl = None
        x, y, w, h, alpha, flip, frames, _state = self.place(kind, rel, atl)
        if forced_flip:
            flip = 1
        self.emit(["scene", rel, kind, arg, x, y, w, h, alpha, flip, frames])
        # A scene replaces the master layer.
        self.tag_state = dict((k, v) for k, v in self.tag_state.items() if k[0] != "master")

    def emit_show(self, node):
        spec = getattr(node, "imspec", None)
        if not spec or not spec[0]:
            self.unsupported["show-empty"] += 1
            return
        parts = tuple(as_text(part) for part in spec[0])
        tag = as_text(spec[2]) if spec[2] else (parts[0] if parts else "")
        layer = as_text(spec[4]) if spec[4] else "master"
        behind_spec = spec[6] if len(spec) > 6 else None
        behind_tags = []
        if behind_spec:
            if isinstance(behind_spec, (list, tuple)):
                behind_tags = [as_text(x) for x in behind_spec]
            else:
                behind_tags = [as_text(behind_spec)]
        behind = ",".join(t for t in behind_tags if t)

        kind, rel, arg, forced_flip, ok = self.resolve_item(parts)
        atl = getattr(node, "atl", None)
        if forced_flip:
            atl = None
        key = (layer, tag)
        base = self.tag_state.get(key) if atl is None else None
        x, y, w, h, alpha, flip, frames, state = self.place(kind, rel, atl, layer, base)
        if forced_flip:
            flip = 1

        if kind == "movie":
            name = os.path.basename(arg or "").lower()
            match = re.match(r"^(\d{4})end\.webm$", name)
            if match:
                self.emit(["ending", match.group(1)])
                self.skip_next_pause = True
                return

        if not ok:
            # `show lynn` with no attributes re-shows the tag's current image
            # in Ren'Py; keep it instead of blanking the sprite.
            if len(parts) == 1:
                self.emit(["show", "", tag, layer, "keep", "", x, y, w, h, alpha, flip, frames, behind])
            else:
                # Keep the tag so a later hide still works, but draw nothing.
                self.emit(["show", "", tag, layer, "none", "", x, y, w, h, alpha, flip, frames, behind])
            self.tag_state[key] = state
            return

        self.emit(["show", rel, tag, layer, kind, arg, x, y, w, h, alpha, flip, frames, behind])
        self.tag_state[key] = state

    def emit_hide(self, node):
        spec = getattr(node, "imspec", None)
        layer = as_text(spec[4]) if spec and spec[4] else "master"
        if not spec or not spec[0]:
            self.emit(["hide", "", layer])
            self.tag_state = dict((k, v) for k, v in self.tag_state.items() if k[0] != layer)
            return
        parts = tuple(as_text(part) for part in spec[0])
        tag = as_text(spec[2]) if spec[2] else (parts[0] if parts else "")
        self.emit(["hide", tag or "", layer])
        self.tag_state.pop((layer, tag or ""), None)

    # -- menus / if ------------------------------------------------------

    def emit_menu(self, node):
        items = getattr(node, "items", None) or []
        choices = []
        for item in items:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            text, cond, block = item[0], item[1], item[2]
            if block is None:
                continue
            cond_text = as_text(cond)
            if cond_text not in (None, "", "True", "true"):
                # Not present in this game, but keep the condition available.
                choices.append((as_text(text), cond_text, block))
            else:
                choices.append((as_text(text), "True", block))

        placeholder = self.emit(["menu", []])
        compiled = []
        ends = []
        for text, cond_text, block in choices:
            start = len(self.ops)
            compiled.append([text, cond_text, start])
            self.walk_block(block)
            ends.append(self.emit(["jump_abs", -1]))
        after = len(self.ops)
        for idx in ends:
            self.patch(idx, ["jump_abs", after])
        self.patch(placeholder, ["menu", compiled])

    def emit_if(self, node):
        entries = getattr(node, "entries", None) or []
        pairs = []
        for entry in entries:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            pairs.append((as_text(entry[0]) or "False", entry[-1]))

        # All If nodes in this game only append to persistent.endings.  Marking
        # an ending seen twice is harmless, so run the branch in-line.
        if pairs and all("persistent.endings" in cond for cond, _block in pairs):
            self.walk_block(pairs[0][1])
            return

        placeholder = self.emit(["if", []])
        compiled = []
        ends = []
        for cond, block in pairs:
            start = len(self.ops)
            compiled.append([cond, start])
            self.walk_block(block)
            ends.append(self.emit(["jump_abs", -1]))
        after = len(self.ops)
        for idx in ends:
            self.patch(idx, ["jump_abs", after])
        self.patch(placeholder, ["if", compiled])

    # -- dialogue / audio / misc ----------------------------------------

    def emit_with(self, node):
        expr = as_text(getattr(node, "expr", None)) or ""
        if self.skip_next_pause:
            self.skip_next_pause = False
            return
        match = WITH_PAUSE_RE.search(expr)
        if match:
            self.emit(["pause", float(match.group(1))])
        # None and other transitions are deliberately ignored.

    def emit_user_statement(self, line):
        text = (line or "").strip()
        if not text:
            return
        match = PLAY_RE.match(text)
        if match:
            channel = match.group(1).lower()
            rel = self.locate_audio(match.group(2))
            fade_match = FADE_RE.search(match.group(3) or "")
            fade = float(fade_match.group(1)) if fade_match else 0.0
            loop = 1 if channel in ("ambient", "music") else 0
            if rel:
                self.emit(["play", channel, rel, fade, loop])
            else:
                self.unresolved_audio[match.group(2)] += 1
                self.emit(["nop"])
            return
        match = STOP_RE.match(text)
        if match:
            channel = match.group(1).lower()
            fade_match = FADE_RE.search(match.group(2) or "")
            fade = float(fade_match.group(1)) if fade_match else 0.0
            self.emit(["stop", channel, fade])
            return
        # show screen / hide screen / window show are handled by the native UI.
        if text.startswith(("show screen", "hide screen", "window ")):
            return
        # `call screen X` waits for a screen and then continues where the
        # screen's action jumps; the Re-Up laptop is the only one used in-story.
        if text.startswith("call screen "):
            name = text[len("call screen "):].strip()
            target = {"search_engine_screen": "scene_0086"}.get(name, "")
            self.emit(["call_screen", name, target])
            return
        self.unsupported["user:" + text.split()[0]] += 1
        self.emit(["nop"])

    def handle_python(self, src):
        src = src or ""
        stripped = src.strip()
        if not stripped:
            return
        try:
            tree = ast.parse(stripped)
        except Exception:
            self.log_unsupported_python(stripped)
            self.emit(["nop"])
            return
        if not tree.body:
            return
        for stmt in tree.body:
            self.handle_py_stmt(stmt, stripped)

    def handle_py_stmt(self, stmt, src):
        if isinstance(stmt, ast.Import) or isinstance(stmt, ast.ImportFrom):
            self.emit(["nop"])
            return

        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            name = dotted_name(call.func)
            if name == "speak":
                who = name_of(call.args[0]) if len(call.args) > 0 else ""
                text = literal(call.args[1]) if len(call.args) > 1 else ""
                display = self.characters.get(who, who)
                self.emit([
                    "say",
                    as_text(display) or "",
                    as_text(text) if text is not None else "",
                    self.wait_start,
                    self.wait_end,
                    self.voice,
                ])
                self.wait_start = -1.0
                self.wait_end = -1.0
                return
            if name == "setWait":
                if len(call.args) >= 2:
                    begin = literal(call.args[0])
                    end = literal(call.args[1])
                    try:
                        self.wait_start = float(begin)
                        self.wait_end = float(end)
                    except Exception:
                        pass
                self.emit(["nop"])
                return
            if name == "setVoiceTrack":
                path = literal(call.args[0]) if call.args else None
                rel = self.locate_audio(as_text(path)) if path is not None else None
                if rel:
                    self.voice = rel
                    self.emit(["voice", rel])
                else:
                    self.unresolved_audio[as_text(path) or "?"] += 1
                    self.emit(["nop"])
                return
            if name == "renpy.movie_cutscene":
                path = literal(call.args[0]) if call.args else None
                rel = self.locate_video(as_text(path)) if path is not None else None
                self.emit(["movie", rel or (as_text(path) or "")])
                return
            if name == "renpy.jump" and call.args:
                # The Re-Up alternates two openings through jump_start_label().
                arg = call.args[0]
                if (isinstance(arg, ast.Call) and
                        dotted_name(arg.func) == "jump_start_label" and len(arg.args) >= 2):
                    first = as_text(literal(arg.args[0]))
                    second = as_text(literal(arg.args[1]))
                    if first and second:
                        self.emit(["start_jump", first, second])
                        return
            if name == "renpy.pause":
                seconds = literal(call.args[0]) if call.args else None
                try:
                    seconds = float(seconds)
                except Exception:
                    seconds = 0.0
                if seconds >= 100.0:
                    # Opening cutscene wait; the native runtime skips movie
                    # playback unless it was built with optional video support.
                    self.emit(["nop"])
                else:
                    self.emit(["pause", seconds])
                return
            if name == "persistent.endings.append" and call.args:
                ending = as_text(literal(call.args[0])) or ""
                match = re.search(r"end_(\d{4})", ending)
                if match:
                    self.emit(["ending_seen", match.group(1)])
                    return
            if name in ("quick_menu",):
                self.emit(["nop"])
                return
            if name in ("killAudio", "game_pause", "game_unpause", "afterLoad"):
                self.emit(["nop"])
                return
            self.unsupported["python:" + (name or "?")] += 1
            self.emit(["nop"])
            return

        if isinstance(stmt, ast.Assign):
            target = dotted_name(stmt.targets[0]) if stmt.targets else ""
            if target == "quick_menu":
                value = literal(stmt.value)
                self.emit(["hud", 1 if value else 0])
                return
            if target == "csbox":
                # The Re-Up's cutscene dialogue: yellow text, no text box.
                value = literal(stmt.value)
                self.emit(["csbox", 1 if value else 0])
                return
            self.emit(["nop"])
            return

        # A relaxed fallback for anything ast cannot classify.
        match = ENDING_APPEND_RE.search(src)
        if match:
            self.emit(["ending_seen", match.group(1)])
            return
        match = QUICK_MENU_RE.search(src)
        if match:
            self.emit(["hud", 1 if match.group(1) == "True" else 0])
            return
        self.log_unsupported_python(src)
        self.emit(["nop"])

    def log_unsupported_python(self, src):
        key = src.strip().split("\n")[0][:60]
        self.unsupported["python:" + key] += 1


def dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return (base + "." + node.attr) if base else node.attr
    return ""


def name_of(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant if hasattr(ast, "Constant") else ast.Str):
        try:
            return as_text(ast.literal_eval(node))
        except Exception:
            return ""
    return ""


def literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# metadata collection
# ---------------------------------------------------------------------------


def collect_metadata(game_dir, files, index, top_nodes):
    image_defs = {}
    transforms = {}
    characters = {}

    def visit(node):
        kind = tname(node)
        if kind == "Image":
            name = getattr(node, "imgname", None)
            if isinstance(name, (list, tuple)):
                key = tuple(as_text(part) for part in name)
            else:
                key = (as_text(name),)
            image_defs[key] = py_source(node) or ""
        elif kind == "Transform":
            var = as_text(getattr(node, "varname", None))
            atl = getattr(node, "atl", None)
            if var and atl is not None:
                props = []
                for st in iter_atl_statements(atl):
                    for key, value in getattr(st, "properties", None) or []:
                        props.append((as_text(key), value))
                transforms[var] = props
        elif kind == "Define":
            var = as_text(getattr(node, "varname", None))
            src = py_source(node) or ""
            if var and "Character(" in src:
                match = CHARACTER_RE.search(src)
                if match:
                    try:
                        characters[var] = as_text(ast.literal_eval(match.group(1))) or var
                    except Exception:
                        characters[var] = var

    walk_nodes(top_nodes, visit)
    return image_defs, transforms, characters


def read_endings(game_dir, index, files, script_source):
    # The Re-Up's ending tracker lives in screens.rpy (seven phone messages),
    # not in an endings/ folder like the first game.
    sidecar = os.path.join(os.path.dirname(os.path.abspath(__file__)), "endings_c09ru.json")
    if os.path.isfile(sidecar):
        with io.open(sidecar, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return dict((entry["id"], entry) for entry in data)

    titles = {}
    scene_list = os.path.join(game_dir, "endings", "00000 SCENE LIST.txt")
    if os.path.isfile(scene_list):
        with io.open(scene_list, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if " - " in line:
                    key, title = line.split(" - ", 1)
                    if re.match(r"^\d{4}$", key.strip()):
                        titles[key.strip()] = title.strip()

    ending_map = {}
    if script_source:
        for match in ENDING_MAP_RE.finditer(script_source):
            ending_map[match.group(1)] = match.group(2)

    def find_epilogue(base):
        rel = index.get(("endings/" + base).lower())
        if rel:
            return rel
        target = re.sub(r"[^a-z0-9]", "", base.lower())
        best = None
        for rel in files:
            low = rel.lower()
            if not low.startswith("endings/") or not low.endswith(".txt"):
                continue
            name = os.path.basename(low)
            if "scene list" in name or name == "completed.txt":
                continue
            candidate = re.sub(r"[^a-z0-9]", "", os.path.splitext(name)[0])
            if candidate == target:
                return rel
            ratio = difflib.SequenceMatcher(None, target, candidate).ratio()
            if best is None or ratio > best[0]:
                best = (ratio, rel)
        if best and best[0] >= 0.80:
            return best[1]
        return None

    endings = {}
    for ending_id in sorted(set(titles.keys()) | set(ending_map.keys())):
        base = ending_map.get(ending_id) or (titles.get(ending_id, ending_id) + ".txt")
        rel = find_epilogue(base)
        text = ""
        if rel and os.path.isfile(os.path.join(game_dir, rel)):
            with io.open(os.path.join(game_dir, rel), "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read().replace("\r\n", "\n").strip()
        endings[ending_id] = {
            "id": ending_id,
            "title": titles.get(ending_id, os.path.splitext(base)[0]),
            "text": text,
        }
    return endings


def build_gui(index):
    def rl(path):
        return index.get(path.lower()) or path

    return {
        "textbox": rl("gui/textbox.png"),
        "textbox_height": 278,
        "textbox_yalign": 1.0,
        "main_menu": rl("gui/main_menu.png"),
        "choice_window": rl("gui/choice_window.png"),
        "choice_idle": rl("gui/button/choice_idle_background.png"),
        "choice_hover": rl("gui/button/choice_hover_background.png"),
        "logo": {"file": rl("gui/ClassOf09logo.png"), "x": 996, "y": 87, "w": 696, "h": 474},
        "name": {
            "x": 360,
            # The paper textbox starts 229px above the bottom edge (y=851);
            # 850 puts the name on the paper, dialogue follows below it.
            "y": 850,
            "font": rl("HELVETICA_EXTRA_COMPRESSED.TTF"),
            "size": 60,
            "color": "#279be8",
        },
        "dialogue": {
            "x": 320,
            "y": 915,
            "w": 1180,
            "font": rl("handwriting2.ttf"),
            "size": 50,
            "line_spacing": -5,
            "color": "#000000",
        },
        "choice": {
            "xalign": 0.47,
            "yalign": 0.3,
            "w": 1185,
            "h": 74,
            "spacing": 33,
            "font": rl("HELVETICA_LT_NARROW.TTF"),
            "size": 60,
            "idle": "#000000",
            "hover": "#AEB88D",
        },
        "menu": {
            "font": rl("FUTURA.TTF"),
            "size": 60,
            "idle": "#888888",
            "hover": "#66c1e0",
            "music": rl("audio/menu_piano.mp3"),
        },
    }


def write_report(path, payload, assembler):
    lines = []
    lines.append("Class of '09 exporter report")
    lines.append("format: %s" % payload.get("format"))
    lines.append("ops: %d" % len(payload.get("ops") or []))
    lines.append("labels: %d" % len(payload.get("labels") or {}))
    lines.append("characters: %d" % len(payload.get("characters") or {}))
    lines.append("endings: %d" % len(payload.get("endings") or []))
    lines.append("")
    lines.append("node stats:")
    for key in sorted(payload.get("stats", {}).keys()):
        lines.append("  %-24s %d" % (key, payload["stats"][key]))
    lines.append("")
    lines.append("unsupported:")
    for key in sorted(payload.get("unsupported", {}).keys()):
        lines.append("  %-40s %d" % (key, payload["unsupported"][key]))
    lines.append("")
    lines.append("unresolved images:")
    for key in sorted(assembler.unresolved_images.keys()):
        lines.append("  %-40s %d" % (key, assembler.unresolved_images[key]))
    lines.append("")
    lines.append("unresolved audio:")
    for key in sorted(assembler.unresolved_audio.keys()):
        lines.append("  %-40s %d" % (key, assembler.unresolved_audio[key]))
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(unicode("\n".join(lines) + "\n"))


def compact_ops(payload):
    """Drop no-op placeholders and remap absolute branch targets."""
    ops = payload["ops"]
    total = len(ops)
    new_index = {}
    new_ops = []
    for i, op in enumerate(ops):
        if not op or op[0] == "nop":
            continue
        new_index[i] = len(new_ops)
        new_ops.append(list(op))

    # after[i] = index in new_ops of the first kept op at or after i.
    after = [len(new_ops)] * (total + 1)
    nxt = len(new_ops)
    for i in range(total - 1, -1, -1):
        if i in new_index:
            nxt = new_index[i]
        after[i] = nxt

    for i, op in enumerate(ops):
        if i not in new_index:
            continue
        target = new_ops[new_index[i]]
        kind = op[0]
        if kind == "jump_abs" and op[1] >= 0:
            target[1] = after[min(op[1], total)]
        elif kind in ("menu", "if"):
            entries = []
            for entry in op[1]:
                entry = list(entry)
                entry[-1] = after[min(entry[-1], total)]
                entries.append(entry)
            target[1] = entries

    labels = {}
    for name, old in payload.get("labels", {}).items():
        labels[name] = after[min(old, total)]
    payload["labels"] = labels
    payload["ops"] = new_ops
    return payload


def main():
    here = os.path.abspath(os.path.dirname(__file__))
    project = os.path.abspath(os.path.join(here, os.pardir))
    default_game = os.path.abspath(os.path.join(project, os.pardir, "Class of 09", "game"))
    game_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else default_game)
    out_dir = os.path.join(project, "build")
    if not os.path.isdir(game_dir):
        sys.stderr.write("Game directory not found: %s\n" % game_dir)
        return 1

    files = []
    index = {}
    for root, _dirs, names in os.walk(game_dir):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), game_dir).replace("\\", "/")
            files.append(rel)
            index[rel.lower()] = rel

    script_path = os.path.join(game_dir, "script.rpyc")
    if not os.path.isfile(script_path):
        sys.stderr.write("Missing %s\n" % script_path)
        return 1

    _data, statements = read_rpyc(script_path)
    image_defs, transforms, characters = collect_metadata(game_dir, files, index, statements)

    script_source = ""
    def collect_py(node):
        src = py_source(node)
        if src:
            collect_source.append(src)
    collect_source = []
    walk_nodes(statements, collect_py)
    script_source = "\n".join(collect_source)

    endings = read_endings(game_dir, index, files, script_source)

    assembler = Assembler(game_dir, files, index, image_defs, transforms, characters, endings)
    payload = assembler.assemble(statements)
    payload["gui"] = build_gui(index)

    animations = {}
    smoke_dir = os.path.join(game_dir, "smokeloop")
    if os.path.isdir(smoke_dir):
        smoke = sorted("smokeloop/" + name for name in os.listdir(smoke_dir)
                       if name.lower().endswith(".png"))
        if smoke:
            animations["smoke"] = {"frames": smoke, "delay_ms": 80}
    payload["animations"] = animations
    compact_ops(payload)

    # Report jump targets that do not exist.
    missing = collections.Counter()
    for op in payload["ops"]:
        if op and op[0] in ("jump", "call") and op[1] not in payload["labels"]:
            missing[op[1]] += 1
    if missing:
        payload["unsupported"]["missing-labels"] = sum(missing.values())
        for name, count in missing.items():
            sys.stderr.write("Missing label: %r (%d)\n" % (name, count))

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    out_path = os.path.join(out_dir, "script.json")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not isinstance(text, unicode):
        text = text.decode("utf-8")
    with io.open(out_path, "w", encoding="utf-8") as handle:
        handle.write(text)

    write_report(os.path.join(out_dir, "export_report.txt"), payload, assembler)

    print("Wrote", out_path)
    print("ops", len(payload["ops"]), "labels", len(payload["labels"]))
    print("characters", len(payload["characters"]), "endings", len(payload["endings"]))
    print("unresolved images", dict(assembler.unresolved_images))
    print("unresolved audio", dict(assembler.unresolved_audio))
    print("unsupported", dict(payload["unsupported"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
