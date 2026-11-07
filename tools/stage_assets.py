#!/usr/bin/env python3
"""Stage The Re-Up's assets into kit/assets for the PS5 package.

    python3 tools/stage_assets.py <game-dir> <build-dir> <kit-assets-dir>

Copies only what the runtime loads: the images/audio the bytecode references,
the GUI art (including the menu buttons and ending tracker), the laptop screen,
the fonts, and the video packs.  Writes GAME_FILES.txt.
"""
import json
import os
import re
import shutil
import sys

GAME = os.path.abspath(sys.argv[1])
BUILD = os.path.abspath(sys.argv[2])
ASSETS = os.path.abspath(sys.argv[3])

FONTS = [
    "handwriting2.ttf",
    "HELVETICA_EXTRA_COMPRESSED.TTF",
    "HELVETICA_LT_NARROW.TTF",
    "FUTURA.TTF",
    "joystix monospace.ttf",
    "texting2007.ttf",
    "DejaVuSans.ttf",
]

GUI_DIRS = [
    "gui/menu 2",
    "gui/ending_tracker",
    "gui/button",
]
GUI_FILES = [
    "gui/textbox.png",
    "gui/namebox.png",
    "gui/main_menu.png",
    "gui/choice_window.png",
    "gui/nvl.png",
    "gui/ClassOf09logo.png",
    "gui/back_pills_vert.png",
    "gui/pause_phone.png",
]


def main():
    script = json.load(open(os.path.join(BUILD, "script.json"), encoding="utf-8"))
    wanted = set()

    for op in script["ops"]:
        kind = op[0]
        if kind in ("show", "scene") and len(op) > 1 and op[1]:
            wanted.add(op[1])
        elif kind == "play" and len(op) > 2:
            wanted.add(op[2])
        elif kind == "voice" and len(op) > 1:
            wanted.add(op[1])

    gui = script.get("gui", {})
    for key in ("textbox", "main_menu", "choice_window", "choice_idle", "choice_hover"):
        if gui.get(key):
            wanted.add(gui[key])
    if gui.get("logo", {}).get("file"):
        wanted.add(gui["logo"]["file"])
    if gui.get("menu", {}).get("music"):
        wanted.add(gui["menu"]["music"])

    wanted.update(GUI_FILES)
    wanted.update(FONTS)

    # Every sound effect the runtime itself plays.
    engine = open(os.path.join(os.path.dirname(ASSETS), "..", "src", "engine.c"),
                  encoding="utf-8", errors="replace").read()
    for m in re.finditer(r'"(audio/[^"]+\.mp3)"', engine):
        wanted.add(m.group(1))

    # All audio (menu, phone, ambience) and the extra GUI folders.
    for root, _dirs, names in os.walk(os.path.join(GAME, "audio")):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), GAME).replace("\\", "/")
            if name.lower().endswith(".mp3"):
                wanted.add(rel)
    for folder in GUI_DIRS:
        base = os.path.join(GAME, folder)
        for root, _dirs, names in os.walk(base):
            for name in names:
                rel = os.path.relpath(os.path.join(root, name), GAME).replace("\\", "/")
                wanted.add(rel)
    for root, _dirs, names in os.walk(os.path.join(GAME, "laptopsearch")):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), GAME).replace("\\", "/")
            wanted.add(rel)

    if os.path.isdir(ASSETS):
        shutil.rmtree(ASSETS)
    game_out = os.path.join(ASSETS, "game")
    os.makedirs(game_out)

    copied = []
    missing = []
    for rel in sorted(wanted):
        src = os.path.join(GAME, rel)
        if not os.path.isfile(src):
            missing.append(rel)
            continue
        dst = os.path.join(game_out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)

    # Bytecode + video packs.
    shutil.copy2(os.path.join(BUILD, "script.json"), os.path.join(ASSETS, "script.json"))
    vids = os.path.join(BUILD, "videos")
    packs_out = os.path.join(ASSETS, "videos", "packs")
    os.makedirs(packs_out, exist_ok=True)
    for name in os.listdir(vids):
        src = os.path.join(vids, name)
        if not os.path.isfile(src):
            continue
        if name.endswith(".mp3"):
            shutil.copy2(src, os.path.join(ASSETS, "videos", name))
    packs_src = os.path.join(vids, "packs")
    if os.path.isdir(packs_src):
        for name in os.listdir(packs_src):
            src = os.path.join(packs_src, name)
            if os.path.isfile(src) and name.endswith(".pkv"):
                shutil.copy2(src, os.path.join(packs_out, name))

    with open(os.path.join(os.path.dirname(ASSETS), "GAME_FILES.txt"), "w", encoding="utf-8") as f:
        for rel in copied:
            f.write(rel + "\n")

    total = 0
    for root, _dirs, names in os.walk(ASSETS):
        for name in names:
            total += os.path.getsize(os.path.join(root, name))
    print("staged %d game files, %.1f MB total" % (len(copied), total / 1048576.0))
    if missing:
        print("missing (%d):" % len(missing))
        for rel in missing[:20]:
            print("  " + rel)


if __name__ == "__main__":
    main()
