# Class of '09 - build entry points.
#
# The PS5 app is built by kit/build_class09.sh inside WSL2. It produces a
# directory-style signed app (eboot.bin + sce_sys/ + sce_module/ + assets/),
# which is what ShadowMountPlus launches.
#
#   make app     build the PS5 app folder and copy it to dist/
#   make host    build the Windows smoke-test runtime (build-cmake/)
#   make check   verify libc imports against the clean-room runtime
#   make clean   remove build outputs (keeps dist/)

SHELL := /bin/bash
PS5_HOST ?= ps5

.DEFAULT_GOAL := app

app:
	bash kit/build_class09.sh
	python3 kit/tools/check-app-imports.py

host:
	cmake --build build-cmake

check:
	python3 kit/tools/check-app-imports.py

# Legacy payload target kept for people with an existing ELF loader: it simply
# reports that the folder build is the supported path.
elf:
	@echo "The supported build is 'make app' (folder app for ShadowMountPlus)."
	@echo "A raw ps5-payload-sdk ELF is no longer produced."
	@exit 1

# Upload the app folder over the usual 2121 FTP server.
upload: app
	@echo "Upload with an FTP client:"
	@echo "  dist/PPSA09009/  ->  /data/homebrew/PPSA09009/"

clean:
	ninja -C kit/build -t clean 2>/dev/null || true
	cmake --build build-cmake --target clean 2>/dev/null || true
