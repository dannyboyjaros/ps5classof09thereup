#!/usr/bin/env bash
# pack_one.sh <input.webm> <out-dir> <name> [height] [q] [fps]
set -euo pipefail
SRC=$1
OUT=$2
NAME=$3
HEIGHT=${4:-720}
Q=${5:-10}
FPS=${6:-30}
mkdir -p "$OUT/packs"
w=$(mktemp -d)
trap 'rm -rf "$w"' EXIT
ffmpeg -y -v error -i "$SRC" -vf "fps=$FPS,scale=-2:$HEIGHT:flags=lanczos" -q:v "$Q" "$w/f_%05d.jpg"
ffmpeg -y -v error -i "$SRC" -vn -c:a libmp3lame -b:a 128k "$OUT/$NAME.mp3" 2>/dev/null || true
python3 - "$w" "$OUT/packs/$NAME.pkv" "$FPS" <<'PY'
import glob, os, struct, sys
frames_dir, out_path, fps = sys.argv[1], sys.argv[2], int(sys.argv[3])
files = sorted(glob.glob(os.path.join(frames_dir, "f_*.jpg")))
blobs, offsets, pos = [], [], 0
for path in files:
    data = open(path, "rb").read()
    blobs.append(data); offsets.append(pos); pos += len(data)
first = open(files[0], "rb").read(65536)
w = h = 0; i = 2
while i + 9 < len(first):
    if first[i] != 0xFF: i += 1; continue
    m = first[i + 1]
    if m in (0xC0, 0xC1, 0xC2):
        h = (first[i + 5] << 8) | first[i + 6]; w = (first[i + 7] << 8) | first[i + 8]; break
    if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7: i += 2; continue
    i += 2 + ((first[i + 2] << 8) | first[i + 3])
with open(out_path, "wb") as out:
    out.write(struct.pack("<4sIIIIII", b"C09V", 1, w, h, fps, len(blobs), 0))
    out.write(struct.pack("<%dI" % len(offsets), *offsets))
    for b in blobs: out.write(b)
print("%s: %d frames %dx%d fps=%d %.1f MB" % (os.path.basename(out_path), len(blobs), w, h, fps, os.path.getsize(out_path)/1048576.0))
PY
