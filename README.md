# Class of '09: The Re-Up — unofficial PS5 homebrew runtime

A native PS5 homebrew app that runs **Class of '09: The Re-Up** from assets you
already own. It is not Ren'Py and not a Sony product. The game's `.rpyc`
scripts are decompiled once into a compact bytecode file, and a small C runtime
interprets that bytecode on the console using the PS5's VideoOut, Pad, and
AudioOut services.

Built on the **Class of '09 (first game) PS5 runtime by CatsAndGats**, adapted
for The Re-Up: cutscene dialogue, the A/B opening rotation, the laptop search
screen, the seven-message ending tracker, and real video playback.

- Title ID: **PPSA09010**
- App folder: `kit/dist/PPSA09010/`
- Content ID: `UP0000-PPSA09010_00-CLASS09RUPS5HOME`

## What works

- Native main menu using The Re-Up's own navigation art, over its animated
  background video, with the game's logo
- Boot splash: `WCsplash.webm` then `logosplash.webm`
- All **163 labels** and **5,543 voiced lines** with the game's timed voice
  tracks (every line auto-advances on the voice's clock; Cross advances early)
- **30 choice menus** with their conditions
- Every background, sprite, flip, and sampled ATL slide/fade, plus the
  120-frame smoke overlay
- **All 12 videos** (opening narration, WCsplash, logosplash, 7 ending videos,
  the secret cs0999 video, and the animated main-menu background) decoded
  directly from the game's original VP8 + Vorbis `.webm` files with libvpx and
  libvorbis — no frame extraction and no pre-converted media
- Cutscene dialogue: yellow Helvetica, no text box (`csbox`)
- The laptop `search_engine_screen` with its hotspot art
- The 7-message ending tracker (Sidekick art, message list, full text view)
- Voice, ambient loops, menu music, and UI sound effects
- 36 save slots with thumbnails, save/load, options, and About
- DualSense and keyboard input

## What is not perfect

- Not Ren'Py: screens, the phone/PDA quick menu, arbitrary Python, and custom
  transitions are not interpreted. Only the subset the exporter emits runs.
- Video is decoded in software with libvpx (VP8) and libvorbis (audio). The PS5
  CPU handles 1080p30 comfortably; the console build links the PS5 static
  libraries vendored under `kit/third_party/webm/`.
- Hardware-verified on a retail PS5 (kernel 5.50): menu, videos, dialogue,
  choices, rollback, quick-menu art, and the ending tracker all run.
  Audio output is wired through the console mixer but was not listened to
  remotely.

### WebM playback

`src/webm.c` is a small Matroska demuxer for exactly what these files use:
EBML, Segment/Info/Tracks/Cluster, SimpleBlock/Block and Xiph lacing. VP8
frames go to libvpx; the Vorbis track is decoded once to a temporary WAV in
`/download0/saves` for the mixer, then removed. The engine prefers the `.webm`
files and only falls back to C09V frame packs if someone still has them.

## Build

The pipeline mirrors the first-game port. Work from the repository root.

### 1. Decompile and export the bytecode

The exporter reads the game's `.rpyc` with the bundled Python 2.7 (Ren'Py 7.5
pickle layout):

```powershell
"..\Class of 09 The Re Up\lib\py2-windows-x86_64\python.exe" tools\export_script.py "..\Class of 09 The Re Up\game"
```

Output: `build/script.json` (10,237 ops, 163 labels, 7 endings, 0 unsupported).

### 2. Stage the assets

```bash
python3 tools/stage_assets.py "/mnt/c/.../game" build kit/assets
```

Writes `kit/assets/script.json`, `kit/assets/game/` (822 files, ~1.06 GB, the
original `.webm` videos included), and `GAME_FILES.txt`. No ffmpeg step.

### 3. Build the PS5 app (WSL2)

```bash
kit/build_class09.sh
```

Uses the starter pipeline in `kit/` (signed `eboot.bin`, clean-room
`libc.prx`). It links the PS5 libvpx/libvorbis/libogg static libraries from
`kit/third_party/webm/` (BSD). Output: `kit/dist/PPSA09010/` and
`PPSA09010.zip`.

### 4. Host build (SDL2)

The host build uses the same WebM path when libvpx/libvorbis/ogg development
packages and pkg-config are available:

```bash
cmake -S . -B build -G Ninja -DC09_WEBM=ON
cmake --build build
build/class09_runtime build/script.json "/path/to/Class of 09 The Re Up/game"
```

Without `-DC09_WEBM=ON` the host build still runs, using C09V frame packs if
present (none are needed for the PS5 app). Saves and screenshots go to
`build/saves`.

## Controls

| Action | DualSense | Keyboard |
| --- | --- | --- |
| Advance / confirm | Cross | Enter / Space |
| Step back one line | Circle | Esc |
| Navigate | D-pad | Arrows |
| Pause menu | Options | Tab |
| Ending tracker (main menu) | Square | E |
| Change an option | D-pad left/right | Left/Right |

The in-game quick menu shows the game's own art: the pill-bottle back button at
the bottom left and the phone pause button at the bottom right.

## Diagnostics

- `CLASS09_AUTOSTART=1` starts a new game; `CLASS09_START_LABEL=<label>`
  jumps to a label.
- `CLASS09_TRACKER=1` opens the ending tracker (with `build/saves/seen.txt`).
- `CLASS09_CAPTURE=<ms>` writes one screenshot; F12 takes one on demand.
- `CLASS09_SAVE_DIR=<dir>` overrides the save folder.

## Legal

Class of '09: The Re-Up and its assets belong to their developers and
publishers. This project is for personal use with a copy of the game you own.
Do not upload or redistribute the app folder, its ZIP, or any extracted assets.
The runtime contains no jailbreak, exploit, or DRM-circumvention code.

Unofficial fan project. Not affiliated with the developers, publishers, or
Sony. The first-game runtime this is based on is by **CatsAndGats**.
