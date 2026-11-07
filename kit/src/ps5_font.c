/*
 * TrueType text for the PS5 runtime, backed by stb_truetype.
 *
 * Renders UTF-8 into an SDL-compatible RGBA surface with the colour baked in
 * and coverage in the alpha channel, which is what SDL_ttf's blended mode
 * does and what engine.c expects.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "SDL.h"
#include "SDL_ttf.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define STB_TRUETYPE_IMPLEMENTATION
/* The console runtime has no assert() backend; stb's checks are advisory. */
#define STBTT_assert(x) ((void)0)
#include "stb_truetype.h"

struct TTF_Font {
    unsigned char *data;
    size_t size;
    stbtt_fontinfo info;
    float scale;
    int px;
    int ascent;
    int descent;
    int line_gap;
    int line_skip;
};

static char g_ttf_error[128] = "";

const char *TTF_GetError(void) { return g_ttf_error; }

int TTF_Init(void) { return 0; }

void TTF_Quit(void) {}

static unsigned char *read_whole_file(const char *path, size_t *out_size) {
    FILE *f = fopen(path, "rb");
    long size;
    unsigned char *data;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return NULL;
    }
    size = ftell(f);
    if (size <= 0) {
        fclose(f);
        return NULL;
    }
    rewind(f);
    data = (unsigned char *)malloc((size_t)size);
    if (!data) {
        fclose(f);
        return NULL;
    }
    if (fread(data, 1, (size_t)size, f) != (size_t)size) {
        free(data);
        fclose(f);
        return NULL;
    }
    fclose(f);
    *out_size = (size_t)size;
    return data;
}

TTF_Font *TTF_OpenFont(const char *file, int ptsize) {
    TTF_Font *font;
    int offset;

    if (!file || ptsize <= 0) return NULL;

    font = (TTF_Font *)calloc(1, sizeof(TTF_Font));
    if (!font) return NULL;

    font->data = read_whole_file(file, &font->size);
    if (!font->data) {
        snprintf(g_ttf_error, sizeof(g_ttf_error), "cannot read %s", file);
        free(font);
        return NULL;
    }

    offset = stbtt_GetFontOffsetForIndex(font->data, 0);
    if (offset < 0 || !stbtt_InitFont(&font->info, font->data, offset)) {
        snprintf(g_ttf_error, sizeof(g_ttf_error), "%s is not a usable TrueType font", file);
        free(font->data);
        free(font);
        return NULL;
    }

    font->px = ptsize;
    font->scale = stbtt_ScaleForPixelHeight(&font->info, (float)ptsize);
    stbtt_GetFontVMetrics(&font->info, &font->ascent, &font->descent, &font->line_gap);
    font->line_skip = (int)ceilf((font->ascent - font->descent + font->line_gap) * font->scale);
    if (font->line_skip <= 0) font->line_skip = ptsize;
    return font;
}

void TTF_CloseFont(TTF_Font *font) {
    if (font) {
        free(font->data);
        free(font);
    }
}

int TTF_FontLineSkip(const TTF_Font *font) {
    return font ? font->line_skip : 0;
}

/* Decode one UTF-8 sequence; invalid bytes become U+FFFD. */
static unsigned next_codepoint(const unsigned char **at) {
    const unsigned char *s = *at;
    unsigned c = s[0];
    if (c < 0x80) {
        *at = s + 1;
        return c;
    }
    if ((c & 0xE0) == 0xC0 && (s[1] & 0xC0) == 0x80) {
        *at = s + 2;
        return ((c & 0x1F) << 6) | (s[1] & 0x3F);
    }
    if ((c & 0xF0) == 0xE0 && (s[1] & 0xC0) == 0x80 && (s[2] & 0xC0) == 0x80) {
        *at = s + 3;
        return ((c & 0x0F) << 12) | ((s[1] & 0x3F) << 6) | (s[2] & 0x3F);
    }
    if ((c & 0xF8) == 0xF0) {
        *at = s + 4;
        return 0xFFFD;
    }
    *at = s + 1;
    return 0xFFFD;
}

typedef struct {
    int width;
    int height;
    int baseline;
} Metrics;

static void measure(TTF_Font *font, const char *text, Metrics *m) {
    const unsigned char *at = (const unsigned char *)text;
    float x = 0;
    int prev = -1;
    if (!text || !text[0]) {
        m->width = 0;
        m->height = font->line_skip;
        m->baseline = (int)ceilf(font->ascent * font->scale);
        return;
    }
    while (*at) {
        unsigned cp = next_codepoint(&at);
        int advance = 0, bearing = 0;
        stbtt_GetCodepointHMetrics(&font->info, (int)cp, &advance, &bearing);
        if (prev >= 0) {
            x += stbtt_GetCodepointKernAdvance(&font->info, prev, (int)cp);
        }
        x += (float)advance;
        prev = (int)cp;
    }
    m->width = (int)ceilf(x * font->scale);
    if (m->width < 1) m->width = 1;
    m->height = font->line_skip;
    m->baseline = (int)ceilf(font->ascent * font->scale);
}

int TTF_SizeUTF8(TTF_Font *font, const char *text, int *w, int *h) {
    Metrics m;
    if (!font) return -1;
    measure(font, text, &m);
    if (w) *w = m.width;
    if (h) *h = m.height;
    return 0;
}

SDL_Surface *TTF_RenderUTF8_Blended(TTF_Font *font, const char *text, SDL_Color color) {
    SDL_Surface *surface;
    Metrics m;
    const unsigned char *at;
    float pen_x;
    int prev = -1;
    Uint32 *pixels;
    unsigned char *bitmap;

    if (!font) return NULL;

    measure(font, text, &m);
    surface = SDL_CreateRGBSurfaceWithFormat(0, m.width, m.height, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!surface) return NULL;

    pixels = (Uint32 *)surface->pixels;
    memset(pixels, 0, (size_t)m.width * (size_t)m.height * 4u);

    bitmap = (unsigned char *)malloc((size_t)m.width * (size_t)m.height);
    if (!bitmap) {
        SDL_FreeSurface(surface);
        return NULL;
    }
    memset(bitmap, 0, (size_t)m.width * (size_t)m.height);

    at = (const unsigned char *)text;
    pen_x = 0.0f;
    while (*at) {
        unsigned cp = next_codepoint(&at);
        int advance = 0, bearing = 0;
        int gx0, gy0, gx1, gy1;
        int gw, gh;
        float fx, fy;

        stbtt_GetCodepointHMetrics(&font->info, (int)cp, &advance, &bearing);
        if (prev >= 0) {
            pen_x += stbtt_GetCodepointKernAdvance(&font->info, prev, (int)cp);
        }

        stbtt_GetCodepointBitmapBoxSubpixel(&font->info, (int)cp, font->scale, font->scale, 0, 0,
                                            &gx0, &gy0, &gx1, &gy1);
        gw = gx1 - gx0;
        gh = gy1 - gy0;

        (void)bearing;
        fx = pen_x * font->scale;
        fy = (float)m.baseline + (float)gy0;

        if (gw > 0 && gh > 0) {
            int gx = (int)floorf(fx);
            int gy = (int)floorf(fy);
            int px, py;
            unsigned char *glyph = (unsigned char *)malloc((size_t)gw * (size_t)gh);
            if (glyph) {
                stbtt_MakeCodepointBitmapSubpixel(&font->info, glyph, gw, gh, gw, font->scale,
                                                  font->scale, 0, 0, (int)cp);
                for (py = 0; py < gh; py++) {
                    int ty = gy + py;
                    if (ty < 0 || ty >= m.height) continue;
                    for (px = 0; px < gw; px++) {
                        int tx = gx + px;
                        if (tx < 0 || tx >= m.width) continue;
                        {
                            unsigned cov = glyph[(size_t)py * gw + px];
                            unsigned char *slot = &bitmap[(size_t)ty * m.width + tx];
                            if (cov > *slot) *slot = (unsigned char)cov;
                        }
                    }
                }
                free(glyph);
            }
        }

        pen_x += (float)advance;
        prev = (int)cp;
    }

    {
        int i, n = m.width * m.height;
        for (i = 0; i < n; i++) {
            unsigned cov = bitmap[i];
            if (cov) {
                pixels[i] = (cov << 24) | ((Uint32)color.b << 16) | ((Uint32)color.g << 8) |
                            (Uint32)color.r;
            }
        }
    }
    free(bitmap);
    return surface;
}
