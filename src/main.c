#include "engine.h"

#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    const char *script = argc > 1 ? argv[1] : NULL;
    const char *game_dir = argc > 2 ? argv[2] : NULL;
    Engine *engine;

    engine = (Engine *)calloc(1, sizeof(Engine));
    if (!engine) {
        fprintf(stderr, "class09: out of memory while creating the runtime\n");
        return 1;
    }

    if (!engine_init(engine, script, game_dir)) {
        fprintf(stderr, "class09: failed to start the runtime\n");
        free(engine);
        return 1;
    }

    while (engine_frame(engine)) {
    }

    engine_shutdown(engine);
    free(engine);
    return 0;
}
