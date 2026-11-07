#!/usr/bin/env bash
# Build video frame packs for the PS5 runtime.
#
#   prepare_video_packs.sh <game-dir> <out-dir> [height] [jpeg-quality]
#
# Each .webm becomes <out>/<name>.pkv (header + JPEG frame offsets) and
# <out>/<name>.mp3 (audio).  Defaults: 1280x720, ffmpeg -q:v 8
# (~1.3 GB for all 10 min of The Re-Up).  Use 1920 4 for maximum quality
# (~2.1 GB) or 960 10 for a smaller package (~600 MB).
#
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

GAME=${1:?usage: prepare_video_packs.sh <game-dir> <out-dir> [height] [q]}
OUT=${2:?usage: prepare_video_packs.sh <game-dir> <out-dir> [height] [q]}
HEIGHT=${3:-720}
Q=${4:-8}

mkdir -p "$OUT/packs"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

for src in "$GAME"/*.webm; do
  name=$(basename "$src" .webm)
  echo "== $name"
  rm -rf "$work/frames"
  mkdir -p "$work/frames"

  # Keep the source frame rate; scale to the requested height.
  ffmpeg -y -v error -i "$src" \
    -vf "scale=-2:$HEIGHT:flags=lanczos" -q:v "$Q" \
    "$work/frames/f_%05d.jpg"

  ffmpeg -y -v error -i "$src" -vn -c:a libmp3lame -b:a 128k "$OUT/$name.mp3" || true

  python3 - "$work/frames" "$OUT/packs/$name.pkv" "$HEIGHT" <<'PY'
import glob, os, struct, sys

frames_dir, out_path, height = sys.argv[1], sys.argv[2], int(sys.argv[3])
files = sorted(glob.glob(os.path.join(frames_dir, "f_*.jpg")))
if not files:
    raise SystemExit("no frames extracted")
blobs = []
offsets = []
pos = 0
for path in files:
    data = open(path, "rb").read()
    blobs.append(data)
    offsets.append(pos)
    pos += len(data)
first = open(files[0], "rb").read(65536)
# Read the JPEG dimensions from the SOF0/SOF2 marker.
w = h = 0
i = 2
while i + 9 < len(first):
    if first[i] != 0xFF:
        i += 1
        continue
    marker = first[i + 1]
    if marker in (0xC0, 0xC1, 0xC2):
        h = (first[i + 5] << 8) | first[i + 6]
        w = (first[i + 7] << 8) | first[i + 8]
        break
    if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
        i += 2
        continue
    seglen = (first[i + 2] << 8) | first[i + 3]
    i += 2 + seglen
header = struct.pack("<4sIIIIII", b"C09V", 1, w or 1280, h or height, 30, len(blobs), 0)
with open(out_path, "wb") as out:
    out.write(header)
    out.write(struct.pack("<%dI" % len(offsets), *offsets))
    for blob in blobs:
        out.write(blob)
print("  %s: %d frames %dx%d %.1f MB" % (os.path.basename(out_path), len(blobs), w, h, os.path.getsize(out_path) / 1048576.0))
PY
done

echo
du -sh "$OUT" 2>/dev/null || true
ls -l "$OUT"/packs | tail -n +2
