/*
 * Entry point for the Class of '09 PS5 runtime.
 *
 * The app folder is mounted at /app0 and its writable area at /download0, so
 * the runtime starts with no arguments in the normal case. Arguments are
 * accepted too, which keeps the same sources usable for host smoke tests.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "engine.h"
#include "ps5_trace.h"

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#ifdef __PROSPERO__
/* How much of the platform libc heap this title can actually use. */
static void heap_probe(void) {
    static const size_t sizes[] = {1, 2, 4, 8, 16, 32, 64};
    void *blocks[sizeof(sizes) / sizeof(sizes[0])] = {0};
    size_t total = 0;
    size_t i;

    for (i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
        blocks[i] = malloc(sizes[i] << 20);
        c09_trace("heap: +%u MiB -> %p (total %u MiB)", (unsigned)sizes[i], blocks[i],
                  (unsigned)total);
        if (!blocks[i]) {
            break;
        }
        total += sizes[i];
    }
    for (i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
        free(blocks[i]);
    }
}
#else
static void heap_probe(void) {}
#endif

int main(int argc, char **argv) {
    const char *script = argc > 1 ? argv[1] : NULL;
    const char *game_dir = argc > 2 ? argv[2] : NULL;
    Engine *engine;

    c09_trace("main: entered argc=%d script=%s game=%s", argc, script ? script : "(default)",
              game_dir ? game_dir : "(default)");
    heap_probe();

    engine = (Engine *)calloc(1, sizeof(Engine));
    if (!engine) {
        c09_trace("main: calloc failed");
        _exit(1);
    }
    c09_trace("main: engine allocated (%u bytes)", (unsigned)sizeof(Engine));

    if (!engine_init(engine, script, game_dir)) {
        c09_trace("main: engine_init failed");
        _exit(1);
    }
    c09_trace("main: engine_init ok");

    while (engine_frame(engine)) {
    }
    c09_trace("main: frame loop ended");

    engine_shutdown(engine);
    free(engine);
    c09_trace("main: shutdown complete");
    _exit(0);
}
