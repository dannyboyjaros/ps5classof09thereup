/*
 * PS5 backend for the Class of '09 runtime.
 *
 * Implements the slice of SDL2 that engine.c needs on top of the PS5's
 * VideoOut framebuffer and DualSense pad. No SDL, no GPU: the scene is drawn
 * into a 1920x1080 ARGB buffer and copied to the scanout buffer each frame.
 *
 * Pixel convention: 0xAABBGGRR, matching RGBA8 byte order on little-endian,
 * which is what the starter and ps5-payload-sdk samples use.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "SDL.h"
#include "SDL_image.h"
#include "ps5_trace.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>

/* ------------------------------------------------------------------------- */
/* PS5 system calls (declared here, resolved by the SDK's import stubs)      */
/* ------------------------------------------------------------------------- */
extern size_t sceKernelGetDirectMemorySize(void);
extern int sceKernelAllocateDirectMemory(int64_t search_start, int64_t search_end, size_t length,
                                         size_t alignment, int memory_type,
                                         int64_t *physical_address);
extern int sceKernelMapDirectMemory(void **address, size_t length, int protection, int flags,
                                    int64_t physical_address, size_t alignment);
extern int sceKernelUsleep(uint32_t microseconds);
extern int sceSystemServiceHideSplashScreen(void);

extern int sceVideoOutOpen(int32_t user_id, int32_t bus_type, int32_t index, const void *param);
extern int sceVideoOutSetFlipRate(int32_t handle, int32_t rate);
extern int sceVideoOutSubmitFlip(int32_t handle, int32_t buffer_index, uint32_t flip_mode,
                                 int64_t flip_argument);
extern int sceVideoOutWaitVblank(int32_t handle);
extern void sceVideoOutSetBufferAttribute2(void *attribute, uint64_t pixel_format,
                                           uint32_t tiling_mode, uint32_t width, uint32_t height,
                                           uint64_t option, uint32_t dcc_control,
                                           uint64_t dcc_clear_color);
extern int sceVideoOutRegisterBuffers2(int32_t handle, int32_t set_index, int32_t buffer_index_start,
                                       void *buffers, int32_t buffer_count, void *attribute,
                                       int32_t category, void *option);

extern int sceUserServiceInitialize(const void *params);
extern int sceUserServiceGetInitialUser(int32_t *user_id);
extern int scePadInit(void);
extern int scePadOpen(int32_t user_id, int32_t type, int32_t index, const void *param);
extern int scePadGetHandle(int32_t user_id, int32_t type, int32_t index);
extern int scePadRead(int32_t handle, void *data, int32_t count);

#define SCREEN_W 1920
#define SCREEN_H 1080

#define FRAME_BYTES 0x1000000u
#define MEMORY_BYTES (FRAME_BYTES * 2u)
#define MEMORY_ALIGNMENT 0x200000u
#define MEMORY_TYPE_WC_GARLIC 3
#define MAP_PROTECTION 0x33
#define PIXEL_FORMAT_RGBA8_SRGB 0x8000000022000000ULL

/* VideoOut scans the buffer in 128x128 tiles of 64 KiB, not row by row, and
 * the tiling applies even with tiling_mode 0. Drawing straight into the
 * scanout buffer therefore comes out as pixel soup on the TV; the scene is
 * rendered into a linear surface and swizzled on present. */
#define TILE_BLOCK 128
#define TILE_BLOCKS_X (SCREEN_W / TILE_BLOCK)
#define TILE_BLOCKS_Y ((SCREEN_H + TILE_BLOCK - 1) / TILE_BLOCK)
#define SCANOUT_BYTES ((size_t)TILE_BLOCKS_X * TILE_BLOCKS_Y * 65536u)

typedef struct {
    void *data;
    void *metadata;
    void *reserved0;
    void *reserved1;
} VideoBuffer;

typedef struct {
    uint8_t reserved[80];
} VideoAttribute;

struct SDL_Window {
    int w, h;
    Uint32 flags;
};

struct SDL_Renderer {
    Uint32 *pixels;
    int w, h;
    int direct; /* pixels points into the scanout buffers; do not free */
    Uint8 draw_r, draw_g, draw_b, draw_a;
    SDL_BlendMode draw_blend;
};

struct SDL_Joystick {
    SDL_JoystickID id;
};

struct SDL_GameController {
    SDL_Joystick joystick;
};

static const char *g_error = "";
static Uint64 g_start_ms;

/* Video state. */
static int g_video = -1;
static VideoBuffer g_buffers[2];
static uint8_t *g_memory;
static Uint32 *g_linear; /* 1920x1080 scene surface, tiled into the scanout buffer */
static int g_back;
static int64_t g_frame_no = 2;
static int g_presented;
static Uint64 g_present_count;
static Uint64 g_last_present_ms;
static Uint64 g_frame_total_ms;
static Uint64 g_busy_total_ms;
static unsigned g_frame_samples;
static unsigned g_trigger_check;
static int g_shot_request;

/* Pad state. */
static int g_pad = -1;
static uint32_t g_pad_prev;
static Uint64 g_last_pad_poll;

static SDL_Joystick g_joystick = {1};
static SDL_GameController g_controller = {{1}};

#define QUEUE_SIZE 32
static SDL_Event g_queue[QUEUE_SIZE];
static int g_queue_head, g_queue_tail;

/* ------------------------------------------------------------------------- */
/* helpers                                                                   */
/* ------------------------------------------------------------------------- */
static Uint64 now_ms_internal(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (Uint64)ts.tv_sec * 1000u + (Uint64)ts.tv_nsec / 1000000u;
}

Uint32 SDL_GetTicks(void) { return (Uint32)(now_ms_internal() - g_start_ms); }

const char *SDL_GetError(void) { return g_error; }

static void flush_range(void *address, size_t length) {
    uint8_t *at = (uint8_t *)address;
    uint8_t *end = at + length;
    for (; at < end; at += 64) {
        __asm__ volatile("clflush (%0)" : : "r"(at) : "memory");
    }
    __asm__ volatile("mfence" ::: "memory");
}

static void *xcalloc(size_t count, size_t size) {
    void *p = calloc(count ? count : 1, size ? size : 1);
    return p;
}

/* ------------------------------------------------------------------------- */
/* video                                                                     */
/* ------------------------------------------------------------------------- */
static size_t tiled_offset(unsigned x, unsigned y) {
    Uint32 offset = ((y << 4) & 0x70u) ^ ((y << 5) & 0xf00u) ^ ((y << 9) & 0x1000u) ^
                    ((y << 8) & 0x4000u) ^ ((x << 2) & 0xcu) ^ ((x << 5) & 0x380u) ^
                    ((x << 4) & 0x400u) ^ ((x << 6) & 0x800u) ^ ((x << 9) & 0xa000u);
    Uint32 block_index = (y >> 7) * (Uint32)TILE_BLOCKS_X + (x >> 7);
    return ((size_t)block_index << 16) + offset;
}

/* Swizzle the scene into the tiled scanout buffer in 4x8 pixel groups so the
 * writes into write-combined memory land in address order. */
static void copy_to_tiled(Uint32 *scanout, const Uint32 *scene) {
    uint8_t *bytes = (uint8_t *)scanout;
    int by, bx, y0, x0, yy, xx;

    for (by = 0; by < TILE_BLOCKS_Y; by++) {
        for (bx = 0; bx < TILE_BLOCKS_X; bx++) {
            for (y0 = 0; y0 < TILE_BLOCK; y0 += 8) {
                int top = by * TILE_BLOCK + y0;
                if (top >= SCREEN_H) break;
                for (x0 = 0; x0 < TILE_BLOCK; x0 += 4) {
                    int left = bx * TILE_BLOCK + x0;
                    for (yy = 0; yy < 8 && top + yy < SCREEN_H; yy++) {
                        const Uint32 *src = scene + (size_t)(top + yy) * SCREEN_W + left;
                        for (xx = 0; xx < 4; xx++) {
                            *(Uint32 *)(bytes + tiled_offset((unsigned)(left + xx),
                                                             (unsigned)(top + yy))) = src[xx];
                        }
                    }
                }
            }
        }
    }
}

static int video_start(void) {
    size_t pool;
    int64_t physical = 0;
    int r;

    if (g_video >= 0) {
        return 1;
    }
    c09_trace("video: start");

    (void)sceSystemServiceHideSplashScreen();
    c09_trace("video: splash hidden");

    g_video = sceVideoOutOpen(0xff, 0, 0, NULL);
    if (g_video < 0) {
        c09_trace("video: sceVideoOutOpen failed (0x%x)", (unsigned)g_video);
        g_error = "sceVideoOutOpen failed";
        g_video = -1;
        return 0;
    }
    c09_trace("video: opened handle=%d", (int)g_video);

    pool = sceKernelGetDirectMemorySize();
    c09_trace("video: direct memory pool=%u", (unsigned)pool);
    if (pool < MEMORY_BYTES) {
        g_error = "not enough direct memory for the framebuffer";
        return 0;
    }

    r = sceKernelAllocateDirectMemory(0, (int64_t)pool, MEMORY_BYTES, MEMORY_ALIGNMENT,
                                      MEMORY_TYPE_WC_GARLIC, &physical);
    c09_trace("video: allocate direct memory r=0x%x physical=0x%llx", (unsigned)r,
              (unsigned long long)physical);
    if (r < 0) {
        g_error = "direct-memory allocation failed";
        return 0;
    }

    g_memory = NULL;
    r = sceKernelMapDirectMemory((void **)&g_memory, MEMORY_BYTES, MAP_PROTECTION, 0, physical,
                                 MEMORY_ALIGNMENT);
    c09_trace("video: map direct memory r=0x%x at=%p", (unsigned)r, (void *)g_memory);
    if (r < 0 || !g_memory) {
        g_error = "direct-memory mapping failed";
        return 0;
    }

    memset(g_memory, 0, MEMORY_BYTES);
    c09_trace("video: framebuffer cleared");

    g_linear = (Uint32 *)calloc((size_t)SCREEN_W * (size_t)SCREEN_H, 4);
    if (!g_linear) {
        g_error = "out of memory for the scene surface";
        return 0;
    }
    c09_trace("video: scene surface at=%p", (void *)g_linear);

    g_buffers[0].data = g_memory;
    g_buffers[0].metadata = NULL;
    g_buffers[0].reserved0 = NULL;
    g_buffers[0].reserved1 = NULL;
    g_buffers[1].data = g_memory + FRAME_BYTES;
    g_buffers[1].metadata = NULL;
    g_buffers[1].reserved0 = NULL;
    g_buffers[1].reserved1 = NULL;

    {
        VideoAttribute attribute;
        memset(&attribute, 0, sizeof(attribute));
        (void)sceVideoOutSetFlipRate(g_video, 0);
        sceVideoOutSetBufferAttribute2(&attribute, PIXEL_FORMAT_RGBA8_SRGB, 0, SCREEN_W, SCREEN_H,
                                       0, 0, 0);
        r = sceVideoOutRegisterBuffers2(g_video, 0, 0, g_buffers, 2, &attribute, 0, NULL);
        if (r < 0) {
            g_error = "sceVideoOutRegisterBuffers2 failed";
            return 0;
        }
    }

    if (sceVideoOutSubmitFlip(g_video, 0, 1, 1) < 0) {
        c09_trace("video: initial flip failed");
        g_error = "initial flip failed";
        return 0;
    }
    (void)sceVideoOutWaitVblank(g_video);
    c09_trace("video: initial flip presented");
    g_back = 1;
    g_presented = 1;
    return 1;
}

/* ------------------------------------------------------------------------- */
/* pad                                                                       */
/* ------------------------------------------------------------------------- */
#define PAD_SAMPLE_SIZE 120
#define PAD_SAMPLE_COUNT 32
#define PAD_INTERCEPTED 0x80000000u

#define RAW_UP 0x0010u
#define RAW_RIGHT 0x0020u
#define RAW_DOWN 0x0040u
#define RAW_LEFT 0x0080u
#define RAW_TRIANGLE 0x1000u
#define RAW_CIRCLE 0x2000u
#define RAW_CROSS 0x4000u
#define RAW_SQUARE 0x8000u
#define RAW_OPTIONS 0x0008u

static unsigned char g_pad_samples[PAD_SAMPLE_COUNT][PAD_SAMPLE_SIZE];

static int pad_start(void) {
    int32_t user = -1;
    if (g_pad >= 0) {
        return 1;
    }
    c09_trace("pad: start");
    (void)sceUserServiceInitialize(NULL);
    if (sceUserServiceGetInitialUser(&user) < 0 || user < 0) {
        c09_trace("pad: no initial user");
        return 0;
    }
    c09_trace("pad: user=%d", (int)user);
    if (scePadInit() < 0) {
        c09_trace("pad: scePadInit failed");
        return 0;
    }
    g_pad = scePadOpen(user, 0, 0, NULL);
    if (g_pad < 0) {
        g_pad = scePadGetHandle(user, 0, 0);
    }
    c09_trace("pad: handle=%d", g_pad);
    return g_pad >= 0;
}

static uint32_t pad_read_buttons(void) {
    uint32_t buttons = 0;
    int count, i;
    if (g_pad < 0) {
        return 0;
    }
    count = scePadRead(g_pad, g_pad_samples, PAD_SAMPLE_COUNT);
    for (i = 0; i < count; i++) {
        const unsigned char *s = g_pad_samples[i];
        uint32_t raw = (uint32_t)s[0] | ((uint32_t)s[1] << 8) | ((uint32_t)s[2] << 16) |
                       ((uint32_t)s[3] << 24);
        uint32_t mapped = 0;
        if (raw & PAD_INTERCEPTED) {
            continue;
        }
        if (raw & RAW_UP) mapped |= 1u << 0;
        if (raw & RAW_DOWN) mapped |= 1u << 1;
        if (raw & RAW_LEFT) mapped |= 1u << 2;
        if (raw & RAW_RIGHT) mapped |= 1u << 3;
        if (raw & RAW_CROSS) mapped |= 1u << 4;
        if (raw & RAW_CIRCLE) mapped |= 1u << 5;
        if (raw & RAW_OPTIONS) mapped |= 1u << 6;
        if (raw & RAW_TRIANGLE) mapped |= 1u << 7;
        if (raw & RAW_SQUARE) mapped |= 1u << 8;
        /* Left stick acts as a D-pad. */
        {
            int lx = (int)s[4] - 128;
            int ly = (int)s[5] - 128;
            if (lx < -64) mapped |= 1u << 2;
            if (lx > 64) mapped |= 1u << 3;
            if (ly < -64) mapped |= 1u << 0;
            if (ly > 64) mapped |= 1u << 1;
        }
        buttons |= mapped;
    }
    return buttons;
}

static void queue_push(const SDL_Event *event) {
    int next = (g_queue_head + 1) % QUEUE_SIZE;
    if (next == g_queue_tail) {
        return; /* full: drop the oldest instead */
    }
    g_queue[g_queue_head] = *event;
    g_queue_head = next;
}

static void pump_pad(void) {
    Uint64 now;
    uint32_t now_buttons, pressed;
    int i;

    if (g_pad < 0 && !pad_start()) {
        return;
    }
    now = now_ms_internal();
    if (now - g_last_pad_poll < 8) {
        return;
    }
    g_last_pad_poll = now;

    now_buttons = pad_read_buttons();
    pressed = now_buttons & ~g_pad_prev;
    g_pad_prev = now_buttons;

    for (i = 0; i < 9; i++) {
        SDL_Event event;
        if (!(pressed & (1u << i))) {
            continue;
        }
        memset(&event, 0, sizeof(event));
        event.type = SDL_CONTROLLERBUTTONDOWN;
        switch (i) {
        case 0: event.cbutton.button = SDL_CONTROLLER_BUTTON_DPAD_UP; break;
        case 1: event.cbutton.button = SDL_CONTROLLER_BUTTON_DPAD_DOWN; break;
        case 2: event.cbutton.button = SDL_CONTROLLER_BUTTON_DPAD_LEFT; break;
        case 3: event.cbutton.button = SDL_CONTROLLER_BUTTON_DPAD_RIGHT; break;
        case 4: event.cbutton.button = SDL_CONTROLLER_BUTTON_A; break;
        case 5: event.cbutton.button = SDL_CONTROLLER_BUTTON_B; break;
        case 6: event.cbutton.button = SDL_CONTROLLER_BUTTON_START; break;
        case 7: event.cbutton.button = SDL_CONTROLLER_BUTTON_Y; break;
        default: event.cbutton.button = SDL_CONTROLLER_BUTTON_X; break;
        }
        queue_push(&event);
    }
}

/* ------------------------------------------------------------------------- */
/* window / renderer                                                         */
/* ------------------------------------------------------------------------- */
int SDL_Init(Uint32 flags) {
    (void)flags;
    g_start_ms = now_ms_internal();
    if (!video_start()) {
        return -1;
    }
    (void)pad_start();
    return 0;
}

void SDL_Quit(void) {
    if (g_video >= 0) {
        /* The launch context owns the display; leaving is the shell's job. */
        g_video = -1;
    }
}

int SDL_SetHint(int name, const char *value) {
    (void)name;
    (void)value;
    return 1;
}

SDL_Window *SDL_CreateWindow(const char *title, int x, int y, int w, int h, Uint32 flags) {
    SDL_Window *window = (SDL_Window *)xcalloc(1, sizeof(SDL_Window));
    (void)title;
    (void)x;
    (void)y;
    if (!window) {
        g_error = "out of memory";
        return NULL;
    }
    window->w = w > 0 ? w : SCREEN_W;
    window->h = h > 0 ? h : SCREEN_H;
    window->flags = flags;
    return window;
}

void SDL_DestroyWindow(SDL_Window *window) { free(window); }

Uint32 SDL_GetWindowFlags(SDL_Window *window) { return window ? window->flags : 0; }

int SDL_SetWindowFullscreen(SDL_Window *window, Uint32 flags) {
    if (window) {
        window->flags = (window->flags & ~SDL_WINDOW_FULLSCREEN_DESKTOP) | flags;
    }
    return 0;
}

void SDL_ShowCursor(int toggle) { (void)toggle; }

SDL_Renderer *SDL_CreateRenderer(SDL_Window *window, int index, Uint32 flags) {
    SDL_Renderer *renderer;
    (void)index;
    (void)flags;
    renderer = (SDL_Renderer *)xcalloc(1, sizeof(SDL_Renderer));
    if (!renderer) {
        g_error = "out of memory";
        return NULL;
    }
    renderer->w = window ? window->w : SCREEN_W;
    renderer->h = window ? window->h : SCREEN_H;
    /* Render into the linear scene surface; SDL_RenderPresent swizzles it
     * into the tiled scanout buffer that is not being displayed. */
    if (renderer->w == SCREEN_W && renderer->h == SCREEN_H && g_linear && g_video >= 0) {
        renderer->pixels = g_linear;
        renderer->direct = 1;
    } else {
        renderer->pixels = (Uint32 *)xcalloc((size_t)renderer->w * (size_t)renderer->h, 4);
        if (!renderer->pixels) {
            free(renderer);
            g_error = "out of memory for the framebuffer";
            return NULL;
        }
    }
    renderer->draw_r = renderer->draw_g = renderer->draw_b = 0;
    renderer->draw_a = 255;
    renderer->draw_blend = SDL_BLENDMODE_BLEND;
    c09_trace("renderer: created %dx%d direct=%d pixels=%p", renderer->w, renderer->h,
              renderer->direct, (void *)renderer->pixels);
    return renderer;
}

void SDL_DestroyRenderer(SDL_Renderer *renderer) {
    if (renderer) {
        if (!renderer->direct) {
            free(renderer->pixels);
        }
        free(renderer);
    }
}

int SDL_RenderSetLogicalSize(SDL_Renderer *renderer, int w, int h) {
    (void)renderer;
    (void)w;
    (void)h;
    return 0;
}

int SDL_GetRendererOutputSize(SDL_Renderer *renderer, int *w, int *h) {
    if (w) *w = renderer ? renderer->w : 0;
    if (h) *h = renderer ? renderer->h : 0;
    return 0;
}

int SDL_SetRenderDrawBlendMode(SDL_Renderer *renderer, SDL_BlendMode blend) {
    if (renderer) renderer->draw_blend = blend;
    return 0;
}

int SDL_SetRenderDrawColor(SDL_Renderer *renderer, Uint8 r, Uint8 g, Uint8 b, Uint8 a) {
    if (renderer) {
        renderer->draw_r = r;
        renderer->draw_g = g;
        renderer->draw_b = b;
        renderer->draw_a = a;
    }
    return 0;
}

int SDL_RenderClear(SDL_Renderer *renderer) {
    int i, n;
    Uint32 color;
    if (!renderer) return -1;
    color = ((Uint32)renderer->draw_a << 24) | ((Uint32)renderer->draw_b << 16) |
            ((Uint32)renderer->draw_g << 8) | renderer->draw_r;
    n = renderer->w * renderer->h;
    for (i = 0; i < n; i++) {
        renderer->pixels[i] = color;
    }
    return 0;
}

static void blend_pixel(Uint32 *dst, Uint32 src, unsigned alpha) {
    unsigned dr, dg, db, sr, sg, sb;
    if (alpha == 0) return;
    if (alpha >= 255) {
        *dst = 0xFF000000u | (src & 0x00FFFFFFu);
        return;
    }
    sr = src & 0xFFu;
    sg = (src >> 8) & 0xFFu;
    sb = (src >> 16) & 0xFFu;
    dr = *dst & 0xFFu;
    dg = (*dst >> 8) & 0xFFu;
    db = (*dst >> 16) & 0xFFu;
    dr = (sr * alpha + dr * (255u - alpha)) / 255u;
    dg = (sg * alpha + dg * (255u - alpha)) / 255u;
    db = (sb * alpha + db * (255u - alpha)) / 255u;
    *dst = 0xFF000000u | (db << 16) | (dg << 8) | dr;
}

int SDL_RenderFillRect(SDL_Renderer *renderer, const SDL_Rect *rect) {
    int x0, y0, x1, y1, y, x;
    Uint32 color;
    unsigned alpha;
    if (!renderer || !rect) return -1;

    x0 = rect->x;
    y0 = rect->y;
    x1 = rect->x + rect->w;
    y1 = rect->y + rect->h;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > renderer->w) x1 = renderer->w;
    if (y1 > renderer->h) y1 = renderer->h;
    if (x0 >= x1 || y0 >= y1) return 0;

    alpha = renderer->draw_blend == SDL_BLENDMODE_BLEND ? renderer->draw_a : 255u;
    color = ((Uint32)renderer->draw_b << 16) | ((Uint32)renderer->draw_g << 8) | renderer->draw_r;

    if (alpha >= 255) {
        Uint32 fill = 0xFF000000u | color;
        for (y = y0; y < y1; y++) {
            Uint32 *row = renderer->pixels + (size_t)y * renderer->w;
            for (x = x0; x < x1; x++) row[x] = fill;
        }
    } else {
        for (y = y0; y < y1; y++) {
            Uint32 *row = renderer->pixels + (size_t)y * renderer->w;
            for (x = x0; x < x1; x++) blend_pixel(&row[x], color, alpha);
        }
    }
    return 0;
}

static void texture_measure(SDL_Texture *texture) {
    int x, y;
    int min_x = texture->w;
    int min_y = texture->h;
    int max_x = -1;
    int max_y = -1;
    int opaque = 1;

    for (y = 0; y < texture->h; y++) {
        const Uint32 *row = texture->pixels + (size_t)y * texture->w;
        for (x = 0; x < texture->w; x++) {
            unsigned alpha = row[x] >> 24;
            if (alpha != 0) {
                if (x < min_x) min_x = x;
                if (x > max_x) max_x = x;
                if (y < min_y) min_y = y;
                if (y > max_y) max_y = y;
                if (alpha != 255) opaque = 0;
            } else {
                opaque = 0;
            }
        }
    }

    if (max_x < min_x || max_y < min_y) {
        texture->bbox_x = texture->bbox_y = 0;
        texture->bbox_x1 = texture->bbox_y1 = 0;
    } else {
        texture->bbox_x = min_x;
        texture->bbox_y = min_y;
        texture->bbox_x1 = max_x + 1;
        texture->bbox_y1 = max_y + 1;
    }
    texture->opaque = opaque && texture->bbox_x1 > texture->bbox_x;
}

SDL_Texture *SDL_CreateTextureFromSurface(SDL_Renderer *renderer, SDL_Surface *surface) {
    SDL_Texture *texture;
    size_t bytes;
    (void)renderer;
    if (!surface || !surface->pixels) {
        g_error = "empty surface";
        return NULL;
    }
    texture = (SDL_Texture *)xcalloc(1, sizeof(SDL_Texture));
    if (!texture) {
        g_error = "out of memory";
        return NULL;
    }
    bytes = (size_t)surface->w * (size_t)surface->h * 4u;
    texture->pixels = (Uint32 *)malloc(bytes);
    if (!texture->pixels) {
        free(texture);
        g_error = "out of memory for a texture";
        return NULL;
    }
    memcpy(texture->pixels, surface->pixels, bytes);
    texture->w = surface->w;
    texture->h = surface->h;
    texture->blend = SDL_BLENDMODE_BLEND;
    texture->alpha_mod = 255;
    texture_measure(texture);
    return texture;
}

void SDL_DestroyTexture(SDL_Texture *texture) {
    if (texture) {
        free(texture->pixels);
        free(texture->scaled);
        free(texture);
    }
}

int SDL_SetTextureBlendMode(SDL_Texture *texture, SDL_BlendMode blend) {
    if (texture) texture->blend = blend;
    return 0;
}

int SDL_SetTextureAlphaMod(SDL_Texture *texture, Uint8 alpha) {
    if (texture) texture->alpha_mod = alpha;
    return 0;
}

/* Bilinear sample of a texture at fixed-point 16.16 source coordinates. */
static Uint32 sample_bilinear(const Uint32 *src, int tw, int th, int64_t fx, int64_t fy) {
    int x0, y0, x1, y1;
    int64_t dx, dy;
    Uint32 p00, p10, p01, p11;
    unsigned r, g, b, a;

    x0 = (int)(fx >> 16);
    y0 = (int)(fy >> 16);
    dx = fx & 0xFFFF;
    dy = fy & 0xFFFF;
    if (x0 < 0) { x0 = 0; dx = 0; }
    if (y0 < 0) { y0 = 0; dy = 0; }
    if (x0 > tw - 1) { x0 = tw - 1; dx = 0; }
    if (y0 > th - 1) { y0 = th - 1; dy = 0; }
    x1 = x0 + 1 < tw ? x0 + 1 : x0;
    y1 = y0 + 1 < th ? y0 + 1 : y0;

    p00 = src[(size_t)y0 * tw + x0];
    p10 = src[(size_t)y0 * tw + x1];
    p01 = src[(size_t)y1 * tw + x0];
    p11 = src[(size_t)y1 * tw + x1];

    {
        int64_t w00 = (0x10000 - dx) * (0x10000 - dy);
        int64_t w10 = dx * (0x10000 - dy);
        int64_t w01 = (0x10000 - dx) * dy;
        int64_t w11 = dx * dy;
        int64_t total = (int64_t)0x10000 * 0x10000;

        a = (unsigned)(((p00 >> 24 & 0xFF) * w00 + (p10 >> 24 & 0xFF) * w10 +
                        (p01 >> 24 & 0xFF) * w01 + (p11 >> 24 & 0xFF) * w11) / total);
        r = (unsigned)(((p00 & 0xFF) * w00 + (p10 & 0xFF) * w10 + (p01 & 0xFF) * w01 +
                        (p11 & 0xFF) * w11) / total);
        g = (unsigned)((((p00 >> 8) & 0xFF) * w00 + ((p10 >> 8) & 0xFF) * w10 +
                        ((p01 >> 8) & 0xFF) * w01 + ((p11 >> 8) & 0xFF) * w11) / total);
        b = (unsigned)((((p00 >> 16) & 0xFF) * w00 + ((p10 >> 16) & 0xFF) * w10 +
                        ((p01 >> 16) & 0xFF) * w01 + ((p11 >> 16) & 0xFF) * w11) / total);
    }
    return (a << 24) | (b << 16) | (g << 8) | r;
}

static void blit_texture(SDL_Renderer *renderer, SDL_Texture *texture, const SDL_Rect *dst,
                         int flip) {
    int x, y;
    unsigned mod;

    if (!renderer || !texture || !texture->pixels || !dst) return;
    if (dst->w <= 0 || dst->h <= 0) return;
    if (texture->bbox_x1 <= texture->bbox_x) return;
    mod = texture->alpha_mod;
    if (mod == 0) return;

    if (dst->w == texture->w && dst->h == texture->h) {
        /* 1:1: only the visible part of the texture is touched, and an
         * opaque texture becomes a plain row copy. Most menu art is a
         * full-screen PNG with a small visible region, so this matters. */
        int bx0 = flip ? (texture->w - texture->bbox_x1) : texture->bbox_x;
        int bx1 = flip ? (texture->w - texture->bbox_x) : texture->bbox_x1;
        int cx0 = dst->x + bx0;
        int cy0 = dst->y + texture->bbox_y;
        int cx1 = dst->x + bx1;
        int cy1 = dst->y + texture->bbox_y1;

        if (cx0 < 0) cx0 = 0;
        if (cy0 < 0) cy0 = 0;
        if (cx1 > renderer->w) cx1 = renderer->w;
        if (cy1 > renderer->h) cy1 = renderer->h;
        if (cx0 >= cx1 || cy0 >= cy1) return;

        if (!flip && texture->opaque && mod == 255) {
            for (y = cy0; y < cy1; y++) {
                const Uint32 *src_row = texture->pixels + (size_t)(y - dst->y) * texture->w;
                Uint32 *dst_row = renderer->pixels + (size_t)y * renderer->w;
                memcpy(dst_row + cx0, src_row + (cx0 - dst->x),
                       (size_t)(cx1 - cx0) * sizeof(Uint32));
            }
            return;
        }

        for (y = cy0; y < cy1; y++) {
            const Uint32 *src_row = texture->pixels + (size_t)(y - dst->y) * texture->w;
            Uint32 *dst_row = renderer->pixels + (size_t)y * renderer->w;
            if (flip) {
                for (x = cx0; x < cx1; x++) {
                    Uint32 p = src_row[texture->w - 1 - (x - dst->x)];
                    blend_pixel(&dst_row[x], p, (p >> 24 & 0xFF) * mod / 255u);
                }
            } else {
                for (x = cx0; x < cx1; x++) {
                    Uint32 p = src_row[x - dst->x];
                    blend_pixel(&dst_row[x], p, (p >> 24 & 0xFF) * mod / 255u);
                }
            }
        }
        return;
    }

    /* Scaled: fixed-point bilinear. Clip the destination to the scaled
     * visible region, with a small margin for the sampling footprint. */
    {
        int dx0 = dst->x;
        int dy0 = dst->y;
        int dx1 = dst->x + dst->w;
        int dy1 = dst->y + dst->h;
        int64_t step_x = ((int64_t)texture->w << 16) / dst->w;
        int64_t step_y = ((int64_t)texture->h << 16) / dst->h;
        int64_t max_x = ((int64_t)texture->w << 16) - 1;
        int cx0 = dx0 + (int)(((int64_t)texture->bbox_x * dst->w) / texture->w) - 2;
        int cx1 = dx0 + (int)(((int64_t)texture->bbox_x1 * dst->w) / texture->w) + 2;
        int cy0 = dy0 + (int)(((int64_t)texture->bbox_y * dst->h) / texture->h) - 2;
        int cy1 = dy0 + (int)(((int64_t)texture->bbox_y1 * dst->h) / texture->h) + 2;

        if (cx0 < dx0) cx0 = dx0;
        if (cy0 < dy0) cy0 = dy0;
        if (cx1 > dx1) cx1 = dx1;
        if (cy1 > dy1) cy1 = dy1;
        if (cx0 < 0) cx0 = 0;
        if (cy0 < 0) cy0 = 0;
        if (cx1 > renderer->w) cx1 = renderer->w;
        if (cy1 > renderer->h) cy1 = renderer->h;
        if (cx0 >= cx1 || cy0 >= cy1) return;

        for (y = cy0; y < cy1; y++) {
            Uint32 *dst_row = renderer->pixels + (size_t)y * renderer->w;
            int64_t fy = ((int64_t)(y - dy0) * step_y) + (step_y >> 1);
            for (x = cx0; x < cx1; x++) {
                int64_t fx = ((int64_t)(x - dx0) * step_x) + (step_x >> 1);
                Uint32 p;
                if (flip) fx = max_x - fx;
                if (fx < 0) fx = 0;
                if (fx > max_x) fx = max_x;
                p = sample_bilinear(texture->pixels, texture->w, texture->h, fx, fy);
                blend_pixel(&dst_row[x], p, (p >> 24 & 0xFF) * mod / 255u);
            }
        }
    }
}

int SDL_RenderCopy(SDL_Renderer *renderer, SDL_Texture *texture, const SDL_Rect *src,
                   const SDL_Rect *dst) {
    SDL_Rect full;
    (void)src;
    if (!dst) {
        if (!renderer || !texture) return -1;
        full.x = 0;
        full.y = 0;
        full.w = texture->w;
        full.h = texture->h;
        blit_texture(renderer, texture, &full, 0);
        return 0;
    }
    blit_texture(renderer, texture, dst, 0);
    return 0;
}

int SDL_RenderCopyEx(SDL_Renderer *renderer, SDL_Texture *texture, const SDL_Rect *src,
                     const SDL_Rect *dst, double angle, const void *center, SDL_RendererFlip flip) {
    (void)src;
    (void)angle;
    (void)center;
    if (!dst) return -1;
    blit_texture(renderer, texture, dst, flip & SDL_FLIP_HORIZONTAL);
    return 0;
}

void SDL_RenderPresent(SDL_Renderer *renderer) {
    uint8_t *target;
    size_t bytes;
    Uint64 start_ms, end_ms;

    if (!renderer || !renderer->pixels || g_video < 0) return;

    start_ms = now_ms_internal();
    target = (uint8_t *)g_buffers[g_back].data;
    bytes = (size_t)SCREEN_W * SCREEN_H * 4u;
    if (renderer->pixels == g_linear) {
        copy_to_tiled((Uint32 *)target, g_linear);
        flush_range(target, SCANOUT_BYTES);
    } else if (renderer->w == SCREEN_W && renderer->h == SCREEN_H) {
        memcpy(target, renderer->pixels, bytes);
        flush_range(target, SCANOUT_BYTES);
    } else {
        /* Nearest scale into the scanout buffer (host-sized surfaces only). */
        int x, y;
        Uint32 *out = (Uint32 *)target;
        for (y = 0; y < SCREEN_H; y++) {
            int sy = y * renderer->h / SCREEN_H;
            Uint32 *src_row = renderer->pixels + (size_t)sy * renderer->w;
            for (x = 0; x < SCREEN_W; x++) {
                out[(size_t)y * SCREEN_W + x] = src_row[x * renderer->w / SCREEN_W];
            }
        }
        flush_range(target, SCANOUT_BYTES);
    }

    if (renderer->pixels == g_linear) {
        /* Unattended visual check: dump a few frames where the host can read
         * them. The scene surface is linear, so the BMPs are the real picture. */
        g_present_count++;
        if (g_present_count == 60 || g_present_count == 300 || g_present_count == 600 ||
            g_present_count == 1200) {
            char shot[64];
            snprintf(shot, sizeof(shot), "/data/c09frame%04d.bmp", (int)g_present_count);
            c09_write_bmp(shot, g_linear, SCREEN_W, SCREEN_H);
            c09_trace("shot: wrote %s at frame %d", shot, (int)g_present_count);
        }
        g_trigger_check++;
        if ((g_trigger_check & 31u) == 0) {
            int fd = open("/data/c09shot.req", O_RDONLY);
            if (fd >= 0) {
                close(fd);
                unlink("/data/c09shot.req");
                g_shot_request = 1;
            }
        }
        if (g_shot_request) {
            g_shot_request = 0;
            c09_write_bmp("/data/c09shot.bmp", g_linear, SCREEN_W, SCREEN_H);
            c09_trace("shot: on-demand /data/c09shot.bmp at frame %d", (int)g_present_count);
        }
    }
    if (sceVideoOutSubmitFlip(g_video, g_back, 1, g_frame_no++) < 0) {
        (void)sceKernelUsleep(4000);
    }
    (void)sceVideoOutWaitVblank(g_video);
    end_ms = now_ms_internal();
    g_back ^= 1;

    if (g_last_present_ms != 0) {
        g_frame_total_ms += start_ms - g_last_present_ms;
        g_busy_total_ms += end_ms - start_ms;
        g_frame_samples++;
        if (g_frame_samples == 120) {
            c09_trace("perf: avg %.1f ms/frame (%.1f fps), present %.1f ms",
                      (double)g_frame_total_ms / (double)g_frame_samples,
                      1000.0 * (double)g_frame_samples / (double)g_frame_total_ms,
                      (double)g_busy_total_ms / (double)g_frame_samples);
            g_frame_total_ms = 0;
            g_busy_total_ms = 0;
            g_frame_samples = 0;
        }
    }
    g_last_present_ms = start_ms;
}

int SDL_RenderReadPixels(SDL_Renderer *renderer, const SDL_Rect *rect, Uint32 format, void *pixels,
                         int pitch) {
    int y, w, h;
    (void)format;
    if (!renderer || !pixels) return -1;
    w = rect ? rect->w : renderer->w;
    h = rect ? rect->h : renderer->h;
    for (y = 0; y < h; y++) {
        const Uint32 *src = renderer->pixels + (size_t)((rect ? rect->y : 0) + y) * renderer->w +
                            (rect ? rect->x : 0);
        memcpy((uint8_t *)pixels + (size_t)y * pitch, src, (size_t)w * 4u);
    }
    return 0;
}

/* ------------------------------------------------------------------------- */
/* surfaces                                                                  */
/* ------------------------------------------------------------------------- */
SDL_Surface *SDL_CreateRGBSurfaceWithFormat(Uint32 flags, int w, int h, int depth, Uint32 format) {
    SDL_Surface *surface;
    (void)flags;
    (void)depth;
    if (w <= 0 || h <= 0) return NULL;
    surface = (SDL_Surface *)xcalloc(1, sizeof(SDL_Surface));
    if (!surface) return NULL;
    surface->w = w;
    surface->h = h;
    surface->pitch = w * 4;
    surface->format = format;
    surface->pixels = xcalloc((size_t)w * (size_t)h, 4);
    if (!surface->pixels) {
        free(surface);
        return NULL;
    }
    return surface;
}

void SDL_FreeSurface(SDL_Surface *surface) {
    if (surface) {
        free(surface->pixels);
        free(surface);
    }
}

int SDL_SetSurfaceBlendMode(SDL_Surface *surface, SDL_BlendMode blend) {
    (void)surface;
    (void)blend;
    return 0;
}

int SDL_BlitScaled(SDL_Surface *src, const SDL_Rect *srcrect, SDL_Surface *dst, SDL_Rect *dstrect) {
    int sx0 = 0, sy0 = 0, sw, sh, dx0, dy0, dw, dh, x, y;
    if (!src || !dst || !src->pixels || !dst->pixels) return -1;
    sw = src->w;
    sh = src->h;
    if (srcrect) {
        sx0 = srcrect->x;
        sy0 = srcrect->y;
        sw = srcrect->w;
        sh = srcrect->h;
    }
    dx0 = 0;
    dy0 = 0;
    dw = dst->w;
    dh = dst->h;
    if (dstrect) {
        dx0 = dstrect->x;
        dy0 = dstrect->y;
        dw = dstrect->w;
        dh = dstrect->h;
    }
    if (dw <= 0 || dh <= 0 || sw <= 0 || sh <= 0) return -1;

    for (y = 0; y < dh; y++) {
        int sy = sy0 + y * sh / dh;
        Uint32 *dst_row = (Uint32 *)dst->pixels + (size_t)(dy0 + y) * dst->w + dx0;
        const Uint32 *src_row = (const Uint32 *)src->pixels + (size_t)sy * src->w;
        for (x = 0; x < dw; x++) {
            int sx = sx0 + x * sw / dw;
            dst_row[x] = src_row[sx];
        }
    }
    return 0;
}

static void put_u16(FILE *f, unsigned v) {
    unsigned char b[2];
    b[0] = (unsigned char)(v & 0xFF);
    b[1] = (unsigned char)((v >> 8) & 0xFF);
    fwrite(b, 1, 2, f);
}

static void put_u32(FILE *f, unsigned v) {
    unsigned char b[4];
    b[0] = (unsigned char)(v & 0xFF);
    b[1] = (unsigned char)((v >> 8) & 0xFF);
    b[2] = (unsigned char)((v >> 16) & 0xFF);
    b[3] = (unsigned char)((v >> 24) & 0xFF);
    fwrite(b, 1, 4, f);
}

int SDL_SaveBMP(SDL_Surface *surface, const char *file) {
    FILE *f;
    int row_size, x, y;
    unsigned char *row;
    if (!surface || !file || !surface->pixels) return -1;
    f = fopen(file, "wb");
    if (!f) {
        g_error = "cannot open the bitmap for writing";
        return -1;
    }
    row_size = (surface->w * 3 + 3) & ~3;

    fwrite("BM", 1, 2, f);
    put_u32(f, (unsigned)(14 + 40 + row_size * surface->h));
    put_u16(f, 0);
    put_u16(f, 0);
    put_u32(f, 14 + 40);
    put_u32(f, 40);
    put_u32(f, (unsigned)surface->w);
    put_u32(f, (unsigned)surface->h);
    put_u16(f, 1);
    put_u16(f, 24);
    put_u32(f, 0);
    put_u32(f, (unsigned)(row_size * surface->h));
    put_u32(f, 2835);
    put_u32(f, 2835);
    put_u32(f, 0);
    put_u32(f, 0);

    row = (unsigned char *)xcalloc((size_t)row_size, 1);
    if (!row) {
        fclose(f);
        return -1;
    }
    for (y = surface->h - 1; y >= 0; y--) {
        const Uint32 *src = (const Uint32 *)surface->pixels + (size_t)y * surface->w;
        for (x = 0; x < surface->w; x++) {
            row[x * 3 + 0] = (unsigned char)((src[x] >> 16) & 0xFF); /* B */
            row[x * 3 + 1] = (unsigned char)((src[x] >> 8) & 0xFF);  /* G */
            row[x * 3 + 2] = (unsigned char)(src[x] & 0xFF);         /* R */
        }
        fwrite(row, 1, (size_t)row_size, f);
    }
    free(row);
    fclose(f);
    return 0;
}

/* ------------------------------------------------------------------------- */
/* input / joysticks                                                         */
/* ------------------------------------------------------------------------- */
int SDL_PollEvent(SDL_Event *event) {
    if (!event) return 0;
    if (g_queue_tail == g_queue_head) {
        pump_pad();
    }
    if (g_queue_tail == g_queue_head) {
        return 0;
    }
    *event = g_queue[g_queue_tail];
    g_queue_tail = (g_queue_tail + 1) % QUEUE_SIZE;
    return 1;
}

int SDL_NumJoysticks(void) { return pad_start() ? 1 : 0; }

SDL_bool SDL_IsGameController(int joystick_index) { return joystick_index == 0 ? 1 : 0; }

SDL_GameController *SDL_GameControllerOpen(int joystick_index) {
    if (joystick_index != 0) return NULL;
    return pad_start() ? &g_controller : NULL;
}

void SDL_GameControllerClose(SDL_GameController *controller) { (void)controller; }

SDL_Joystick *SDL_GameControllerGetJoystick(SDL_GameController *controller) {
    (void)controller;
    return &g_joystick;
}

SDL_JoystickID SDL_JoystickInstanceID(SDL_Joystick *joystick) {
    return joystick ? joystick->id : 0;
}
