#!/usr/bin/env bash
# Build the Class of '09 PS5 app through the starter pipeline.
#
# The pipeline runs zlib's configure step, which mishandles paths containing
# spaces. When the kit lives under such a path (the default on this desktop),
# re-execute from a space-free symlink in $HOME instead.
set -euo pipefail

kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ $kit == *" "* ]]; then
    link="$HOME/c09kit"
    ln -sfn "$kit" "$link"
    kit=$(cd -- "$link" && pwd)
fi

cd "$kit"

if [[ ! -x .deps/native/ps5-payload-sdk/bin/prospero-lld ]]; then
    bash tools/setup-native-dependencies.sh
fi

exec env \
    APP_DEFINITIONS=__PROSPERO__ \
    APP_INCLUDE_PATHS='src/sdl src' \
    APP_ASSETS=assets \
    APP_ROOT_FILES='GAME_FILES.txt README-PS5.txt' \
    USE_CCACHE=1 \
    PS5_CLANG="${PS5_CLANG:-clang-18}" \
    bash tools/build.sh Folder
