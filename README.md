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
  the secret cs0999 video, and the animated main-menu background) via 1080p
  JPEG frame packs and MP3 audio (~1.6 GB)
- Cutscene dialogue: yellow Helvetica, no text box (`csbox`)
- The laptop `search_engine_screen` with its hotspot art
- The 7-message ending tracker (Sidekick art, message list, full text view)
- Voice, ambient loops, menu music, and UI sound effects
- 36 save slots with thumbnails, save/load, options, and About
- DualSense and keyboard input

## What is not perfect

- Not Ren'Py: screens, the phone/PDA quick menu, arbitrary Python, and custom
  transitions are not interpreted. Only the subset the exporter emits runs.
- Video is stored as 1080p30 JPEG frames (~1.6 GB for all 10:25) because the
  PS5 homebrew backend has no VP8 decoder. Use `720 8` in
  `tools/prepare_video_packs.sh` for a smaller package (~809 MB).
- Hardware behaviour (`/app0`, `/download0`, audio) is unverified because no
  PS5 was available for testing; the host build is verified.

### Video packs

The pack format is a 28-byte header (`C09V`, version, width, height, fps,
frame count, reserved), a `uint32` offset per frame, then the JPEG frames.
Audio sits beside the pack as an MP3. `IMG_LoadMemory` decodes frames from RAM
on both backends.

## Build

The pipeline mirrors the first-game port. Work from the repository root.

### 1. Decompile and export the bytecode

The exporter reads the game's `.rpyc` with the bundled Python 2.7 (Ren'Py 7.5
pickle layout):

```powershell
"..\Class of 09 The Re Up\lib\py2-windows-x86_64\python.exe" tools\export_script.py "..\Class of 09 The Re Up\game"
```

Output: `build/script.json` (10,237 ops, 163 labels, 7 endings, 0 unsupported).

### 2. Build the video packs (WSL/Linux, needs ffmpeg)

```bash
tools/prepare_video_packs.sh "/mnt/c/.../game" build/videos 1080 8
# the animated main-menu background
tools/pack_one.sh "/mnt/c/.../game/gui/menu 2/BG living.webm" build/videos BG_living 1080 8 30
```

### 3. Stage the assets

```bash
python3 tools/stage_assets.py "/mnt/c/.../game" build kit/assets
```

Writes `kit/assets/script.json`, `kit/assets/game/` (691 files, ~649 MB), the
video packs, and `GAME_FILES.txt`.

### 4. Build the PS5 app (WSL2)

```bash
kit/build_class09.sh
```

Uses the starter pipeline in `kit/` (signed `eboot.bin`, clean-room
`libc.prx`). Output: `kit/dist/PPSA09010/` and `PPSA09010.zip`.

### 5. Host build (Windows, SDL2)

```powershell
cmake -S . -B build -G Ninja -DSDL2_DIR=...
cmake --build build
build\class09_runtime.exe build\script.json "..\Class of 09 The Re Up\game"
```

Saves and screenshots go to `build/saves`.

## Controls

| Action | DualSense | Keyboard |
| --- | --- | --- |
| Advance / confirm | Cross | Enter / Space |
| Back, pause during a scene | Circle | Esc |
| Navigate | D-pad | Arrows |
| In-game menu | Options | Tab |
| Ending tracker (main menu) | Square | T |
| Change an option | D-pad left/right | Left/Right |

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
