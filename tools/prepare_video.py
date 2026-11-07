#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract a Ren'Py .webm into a JPEG frame cache for the runtime splash.

The runtime does not link a video decoder. Instead this tool uses the same
FFmpeg-backed decoder that ships with the user's copy of Class of '09 (through
Ren'Py's ``renpy.audio.renpysound`` module) and writes the frames as JPEGs plus a
small manifest.

The extracted frames come from the user's own game files. Do not redistribute
them with the runtime.

Examples (run from the ps5-homebrew folder):

    "..\\Class of 09\\lib\\py2-windows-x86_64\\python.exe" tools\\prepare_video.py
    "..\\Class of 09\\lib\\py2-windows-x86_64\\python.exe" tools\\prepare_video.py \\
        --video opening --video percpop --out build\\videos

By default this extracts ``logosplash`` into ``build/videos/logosplash``.
Copy the resulting ``videos`` folder to ``/data/class09/videos`` on the console.
"""

from __future__ import print_function

import argparse
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
DEFAULT_GAME = os.path.abspath(os.path.join(ROOT, os.pardir, "Class of 09", "game"))
DEFAULT_OUT = os.path.join(ROOT, "build", "videos")


def fail(message):
    sys.stderr.write("prepare_video: %s\n" % message)
    raise SystemExit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Extract a Ren'Py webm into a JPEG splash cache.")
    parser.add_argument("--game", default=DEFAULT_GAME,
                        help="path to the game/ folder (default: %(default)s)")
    parser.add_argument("--renpy", default=None,
                        help="path to the Ren'Py install root (default: parent of --game)")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="output folder that will contain <video>/frame_*.jpg (default: %(default)s)")
    parser.add_argument("--video", action="append", default=None,
                        help="video name or path, without .webm (default: logosplash). May be repeated.")
    parser.add_argument("--fps", type=int, default=0,
                        help="override the playback rate; 0 reads the WebM container rate (default: 0)")
    parser.add_argument("--width", type=int, default=0,
                        help="scale frames to this width; 0 keeps the source size (default: 0)")
    parser.add_argument("--height", type=int, default=0,
                        help="scale frames to this height; 0 keeps the source size (default: 0)")
    parser.add_argument("--quality", type=int, default=90,
                        help="JPEG quality, 1-100 (default: 90)")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="abort a single video after this many seconds (default: 180)")
    return parser.parse_args()


def setup_renpy(game, renpy_root):
    """Put the Ren'Py runtime and its Python 2.7 stdlib on sys.path."""

    if not os.path.isdir(game):
        fail("game folder not found: %s" % game)
    if renpy_root is None:
        renpy_root = os.path.abspath(os.path.join(game, os.pardir))
    candidates = [renpy_root, os.path.join(renpy_root, "lib", "python2.7")]
    for path in candidates:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    if not os.path.isdir(os.path.join(renpy_root, "renpy")):
        fail("cannot find the renpy package under %s" % renpy_root)
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    return renpy_root


def resolve_video(game, name):
    path = name
    if not os.path.isabs(path) and not os.path.exists(path):
        path = os.path.join(game, name)
    if not os.path.splitext(path)[1]:
        path += ".webm"
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        fail("video not found: %s" % path)
    return path


def clean_frames(outdir):
    if not os.path.isdir(outdir):
        return
    for name in os.listdir(outdir):
        if re.match(r"^frame_\d{4}\.jpg$", name):
            try:
                os.remove(os.path.join(outdir, name))
            except OSError:
                pass


def write_manifest(outdir, fps, frames, width, height):
    path = os.path.join(outdir, "manifest.txt")
    with open(path, "wb") as handle:
        handle.write("fps=%d\n" % fps)
        handle.write("frames=%d\n" % frames)
        handle.write("width=%d\n" % width)
        handle.write("height=%d\n" % height)


def read_vint(data, pos, keep_marker=False):
    """Read a Matroska variable-length integer."""
    if pos >= len(data):
        return None, pos
    first = byte_at(data, pos)
    mask = 0x80
    length = 1
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 8 or pos + length > len(data):
        return None, pos
    value = first if keep_marker else (first & (mask - 1))
    for i in range(1, length):
        value = (value << 8) | byte_at(data, pos + i)
    return value, pos + length


def byte_at(data, pos):
    value = data[pos]
    return ord(value) if isinstance(value, str) else value


def webm_frame_rate(path):
    """Read DefaultDuration (0x23E383) from a Matroska/WebM file.

    The container stores nanoseconds per frame, which is exact. Ren'Py's
    get_duration() reports the decodable stream length rather than the frame
    rate, so it cannot be used for this.
    """
    try:
        data = open(path, "rb").read()
    except IOError:
        return 0.0
    target = b"\x23\xe3\x83"
    start = 0
    while True:
        index = data.find(target, start)
        if index < 0:
            return 0.0
        size, value_pos = read_vint(data, index + 3)
        if size and 1 <= size <= 8 and value_pos + size <= len(data):
            value = 0
            for i in range(size):
                value = (value << 8) | byte_at(data, value_pos + i)
            # Accept 1..1000 fps only; guards against false ID matches.
            if 1000000 <= value <= 1000000000:
                return 1e9 / float(value)
        start = index + 1


def extract(rs, pygame, path, outdir, args):
    """Decode one video and write frame_0000.jpg ... plus a manifest."""

    clean_frames(outdir)
    frame_rate = webm_frame_rate(path)

    # pygame_sdl2 writes through an RWops, and the desktop build cannot create
    # one from a Unicode filename. Work in a plain ASCII directory when needed.
    save_dir = outdir
    if not re.match(r"^[\x00-\x7f]+$", outdir):
        save_dir = os.path.join(os.environ.get("TEMP", "/tmp"), "class09_frames")
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir)
        clean_frames(save_dir)

    rs.set_video(0, rs.NODROP_VIDEO)
    # end=-1 is required: end=0 forces a zero-length stream.
    rs.play(0, path, path, start=0, end=-1)

    start = time.time()
    last_frame = start
    frame_times = []
    frames = 0
    width = 0
    height = 0
    duration = 0.0

    while True:
        now = time.time()
        if now - start > args.timeout:
            fail("timed out after %.0f seconds while decoding %s" % (args.timeout, path))

        rs.advance_time()
        rs.periodic()

        if rs.video_ready(0):
            surface = rs.read_video(0)
            if surface is not None:
                width, height = surface.get_size()
                target = surface
                if args.width or args.height:
                    dst_w = args.width or width
                    dst_h = args.height or height
                    if (dst_w, dst_h) != (width, height):
                        target = pygame.transform.smoothscale(surface, (dst_w, dst_h))
                filename = os.path.join(save_dir, "frame_%04d.jpg" % frames)
                pygame.image.save(target, filename, args.quality)
                frame_times.append(now - start)
                frames += 1
                last_frame = now
                if frames == 1:
                    # The container duration is the reliable source of the frame
                    # rate; wall-clock decode speed depends on the host.
                    try:
                        duration = float(rs.get_duration(0))
                    except Exception:
                        duration = 0.0
                if frames == 1 or frames % 30 == 0:
                    print("  %s: frame %d (%.2fs)" % (os.path.basename(path), frames, now - start))

        if not rs.busy(0):
            break
        time.sleep(0.003)

    if frames == 0:
        fail("no frames decoded from %s" % path)

    if args.fps:
        fps = args.fps
    elif frame_rate > 0.0:
        fps = int(round(frame_rate))
        if fps < 1:
            fps = 1
        if fps > 240:
            fps = 240
    elif duration > 0.1 and frames > 2:
        fps = int(round(frames / duration))
        if fps < 1:
            fps = 1
        if fps > 240:
            fps = 240
    elif len(frame_times) > 2 and frame_times[-1] > frame_times[0]:
        fps = int(round((len(frame_times) - 1) / (frame_times[-1] - frame_times[0])))
        if fps < 1:
            fps = 1
    else:
        fps = 30

    if save_dir != outdir:
        if not os.path.isdir(outdir):
            os.makedirs(outdir)
        for name in os.listdir(save_dir):
            if re.match(r"^frame_\d{4}\.jpg$", name):
                shutil.copyfile(os.path.join(save_dir, name), os.path.join(outdir, name))
        shutil.rmtree(save_dir, ignore_errors=True)

    write_manifest(outdir, fps, frames, width, height)
    print("%s: %d frames, %dx%d, %d fps%s -> %s" % (
        os.path.basename(path), frames, width, height, fps,
        (" (container %.2f)" % frame_rate) if frame_rate > 0.0 else "", outdir))
    return frames


def main():
    args = parse_args()
    game = os.path.abspath(args.game)
    out_root = os.path.abspath(args.out)
    renpy_root = setup_renpy(game, args.renpy)

    try:
        import pygame_sdl2 as pygame
        import renpy.audio.renpysound as rs
    except ImportError as exc:
        fail("cannot import Ren'Py's media modules (%s).\n"
             "Run this with the Python bundled with the game: "
             "lib\\py2-windows-x86_64\\python.exe" % exc)

    # These sample surfaces mirror Ren'Py's set_rgba_masks() so read_video()
    # returns a surface with the right pixel layout on little-endian hosts.
    try:
        pygame.display.init()
    except Exception:
        pass
    rs.init(44100, 2, 2048, True, False)
    probe = pygame.Surface((10, 10), 0, 32)
    alpha = probe.convert_alpha()
    masks = list(alpha.get_masks())
    masks.sort(key=abs)
    if sys.byteorder != "big":
        masks = (masks[0], masks[1], masks[2], masks[3])
    else:
        masks = (masks[3], masks[2], masks[1], masks[0])
    alpha = pygame.Surface((10, 10), 0, 32, masks)
    noalpha = pygame.Surface((10, 10), 0, 32, masks[:3] + (0,))
    rs.sample_surfaces(noalpha, alpha)

    videos = args.video or ["logosplash"]
    ok = 0
    for video in videos:
        path = resolve_video(game, video)
        name = os.path.splitext(os.path.basename(path))[0]
        outdir = os.path.join(out_root, name)
        if not os.path.isdir(outdir):
            os.makedirs(outdir)
        print("decoding %s" % path)
        extract(rs, pygame, path, outdir, args)
        ok += 1

    rs.stop(0)
    try:
        rs.quit()
    except Exception:
        pass
    print("done: %d video(s) written under %s" % (ok, out_root))


if __name__ == "__main__":
    main()
