/*
 * Image loading for the PS5 runtime: PNG, JPEG and BMP through stb_image.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "SDL.h"
#include "SDL_image.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define STB_IMAGE_IMPLEMENTATION
#define STBI_NO_HDR
#define STBI_NO_PIC
#define STBI_NO_PNM
/* The PS5 loader's libc does not provide emulated-TLS helpers, so keep stb's
 * decoder state in ordinary statics. Decoding is single-threaded here. */
#define STBI_NO_THREAD_LOCALS
/* No assert() backend is linked into the console runtime. */
#define STBI_ASSERT(x) ((void)0)
#include "stb_image.h"

static char g_image_error[128] = "";

const char *IMG_GetError(void) { return g_image_error; }

int IMG_Init(int flags) { return flags; }

void IMG_Quit(void) {}

SDL_Surface *IMG_Load(const char *file) {
    SDL_Surface *surface;
    unsigned char *rgba;
    int w = 0, h = 0, channels = 0;

    if (!file) return NULL;

    rgba = stbi_load(file, &w, &h, &channels, 4);
    if (!rgba) {
        const char *why = stbi_failure_reason();
        snprintf(g_image_error, sizeof(g_image_error), "%s", why ? why : "unknown image error");
        return NULL;
    }
    if (w <= 0 || h <= 0) {
        stbi_image_free(rgba);
        return NULL;
    }

    surface = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!surface) {
        stbi_image_free(rgba);
        return NULL;
    }
    /* stb gives R,G,B,A bytes; the runtime's 0xAABBGGRR word has the same
     * byte order on little-endian. */
    memcpy(surface->pixels, rgba, (size_t)w * (size_t)h * 4u);
    stbi_image_free(rgba);
    return surface;
}
