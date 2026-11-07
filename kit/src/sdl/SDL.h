/*
 * Minimal SDL2-compatible surface for the Class of '09 PS5 runtime.
 *
 * This is not SDL. It is a small header that declares exactly the SDL types
 * and entry points engine.c uses, so the runtime can be built for the PS5
 * against a native backend (ps5_backend.c) instead of SDL2.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef CLASS09_SDL_COMPAT_H
#define CLASS09_SDL_COMPAT_H

#include <stddef.h>
#include <stdint.h>

typedef uint8_t Uint8;
typedef int8_t Sint8;
typedef uint16_t Uint16;
typedef int16_t Sint16;
typedef uint32_t Uint32;
typedef int32_t Sint32;
typedef uint64_t Uint64;
typedef int64_t Sint64;
typedef int SDL_bool;

/* ---- events ---- */
enum {
    SDL_QUIT = 0x100,
    SDL_KEYDOWN = 0x300,
    SDL_MOUSEBUTTONDOWN = 0x401,
    SDL_CONTROLLERBUTTONDOWN = 0x605,
    SDL_CONTROLLERDEVICEADDED = 0x653,
    SDL_CONTROLLERDEVICEREMOVED = 0x654
};

typedef int32_t SDL_Keycode;

typedef struct SDL_Keysym {
    int scancode;
    SDL_Keycode sym;
    Uint16 mod;
} SDL_Keysym;

typedef union SDL_Event {
    Uint32 type;
    struct {
        Uint32 type;
        Uint32 timestamp;
        SDL_Keysym keysym;
        Uint8 repeat;
    } key;
    struct {
        Uint32 type;
        Uint32 timestamp;
        Uint8 button;
        Uint8 state;
    } cbutton;
    struct {
        Uint32 type;
        Uint32 timestamp;
        Sint32 which;
    } cdevice;
    struct {
        Uint32 type;
        Uint32 timestamp;
        Uint8 button;
    } button;
} SDL_Event;

/* ---- key codes ---- */
enum {
    SDLK_RETURN = 0x0d,
    SDLK_ESCAPE = 0x1b,
    SDLK_SPACE = 0x20,
    SDLK_TAB = 0x09,
    SDLK_LEFT = 0x40000050,
    SDLK_RIGHT = 0x4000004f,
    SDLK_UP = 0x40000052,
    SDLK_DOWN = 0x40000051,
    SDLK_KP_ENTER = 0x40000058,
    SDLK_KP_4 = 0x4000005c,
    SDLK_KP_6 = 0x4000005e,
    SDLK_KP_8 = 0x40000060,
    SDLK_KP_2 = 0x4000005a,
    SDLK_F9 = 0x40000042,
    SDLK_F11 = 0x40000044,
    SDLK_F12 = 0x40000045,
    SDLK_e = 0x65
};

/* ---- game controller ---- */
enum {
    SDL_CONTROLLER_BUTTON_A = 0,
    SDL_CONTROLLER_BUTTON_B = 1,
    SDL_CONTROLLER_BUTTON_X = 2,
    SDL_CONTROLLER_BUTTON_Y = 3,
    SDL_CONTROLLER_BUTTON_BACK = 4,
    SDL_CONTROLLER_BUTTON_START = 6,
    SDL_CONTROLLER_BUTTON_DPAD_UP = 11,
    SDL_CONTROLLER_BUTTON_DPAD_DOWN = 12,
    SDL_CONTROLLER_BUTTON_DPAD_LEFT = 13,
    SDL_CONTROLLER_BUTTON_DPAD_RIGHT = 14
};

typedef int SDL_JoystickID;
typedef struct SDL_Joystick SDL_Joystick;
typedef struct SDL_GameController SDL_GameController;

/* ---- rectangles / colours ---- */
typedef struct SDL_Rect {
    int x, y, w, h;
} SDL_Rect;

typedef struct SDL_Color {
    Uint8 r, g, b, a;
} SDL_Color;

typedef enum SDL_BlendMode {
    SDL_BLENDMODE_NONE = 0,
    SDL_BLENDMODE_BLEND = 1
} SDL_BlendMode;

typedef enum SDL_RendererFlip {
    SDL_FLIP_NONE = 0,
    SDL_FLIP_HORIZONTAL = 1,
    SDL_FLIP_VERTICAL = 2
} SDL_RendererFlip;

/* ---- video ---- */
typedef struct SDL_Window SDL_Window;
typedef struct SDL_Renderer SDL_Renderer;

typedef struct SDL_Texture {
    int w, h;
    Uint32 *pixels; /* 0xAABBGGRR, row-major */
    int blend;
    Uint8 alpha_mod;
    /* visible region (non-zero alpha) and whether every pixel is opaque */
    int bbox_x, bbox_y, bbox_x1, bbox_y1;
    int opaque;
    /* cached scaled copy for the framebuffer blit */
    int scaled_w, scaled_h;
    Uint32 *scaled;
    int scaled_flip;
} SDL_Texture;

typedef struct SDL_Surface {
    int w, h, pitch;
    void *pixels; /* 0xAABBGGRR */
    Uint32 format;
} SDL_Surface;

enum {
    SDL_INIT_AUDIO = 0x00000010,
    SDL_INIT_VIDEO = 0x00000020,
    SDL_INIT_GAMECONTROLLER = 0x00002000,
    SDL_INIT_EVENTS = 0x00004000
};

enum {
    SDL_WINDOWPOS_CENTERED = 0x2FFF0000,
    SDL_WINDOW_FULLSCREEN = 0x00000001,
    SDL_WINDOW_SHOWN = 0x00000004,
    SDL_WINDOW_RESIZABLE = 0x00000020,
    SDL_WINDOW_FULLSCREEN_DESKTOP = 0x00001001
};

enum {
    SDL_RENDERER_SOFTWARE = 0x00000001,
    SDL_RENDERER_ACCELERATED = 0x00000002,
    SDL_RENDERER_PRESENTVSYNC = 0x00000004
};

enum { SDL_DISABLE = 0, SDL_ENABLE = 1 };
enum { SDL_PIXELFORMAT_ARGB8888 = 0x16362004u };
enum { SDL_HINT_RENDER_SCALE_QUALITY = 1 };

/* ---- entry points used by the runtime ---- */
int SDL_Init(Uint32 flags);
void SDL_Quit(void);
const char *SDL_GetError(void);
int SDL_SetHint(int name, const char *value);

SDL_Window *SDL_CreateWindow(const char *title, int x, int y, int w, int h, Uint32 flags);
void SDL_DestroyWindow(SDL_Window *window);
Uint32 SDL_GetWindowFlags(SDL_Window *window);
int SDL_SetWindowFullscreen(SDL_Window *window, Uint32 flags);
void SDL_ShowCursor(int toggle);

SDL_Renderer *SDL_CreateRenderer(SDL_Window *window, int index, Uint32 flags);
void SDL_DestroyRenderer(SDL_Renderer *renderer);
int SDL_RenderSetLogicalSize(SDL_Renderer *renderer, int w, int h);
int SDL_GetRendererOutputSize(SDL_Renderer *renderer, int *w, int *h);
int SDL_SetRenderDrawBlendMode(SDL_Renderer *renderer, SDL_BlendMode blend);
int SDL_SetRenderDrawColor(SDL_Renderer *renderer, Uint8 r, Uint8 g, Uint8 b, Uint8 a);
int SDL_RenderClear(SDL_Renderer *renderer);
int SDL_RenderFillRect(SDL_Renderer *renderer, const SDL_Rect *rect);
int SDL_RenderCopy(SDL_Renderer *renderer, SDL_Texture *texture, const SDL_Rect *src,
                   const SDL_Rect *dst);
int SDL_RenderCopyEx(SDL_Renderer *renderer, SDL_Texture *texture, const SDL_Rect *src,
                     const SDL_Rect *dst, double angle, const void *center, SDL_RendererFlip flip);
void SDL_RenderPresent(SDL_Renderer *renderer);
int SDL_RenderReadPixels(SDL_Renderer *renderer, const SDL_Rect *rect, Uint32 format, void *pixels,
                         int pitch);

SDL_Surface *SDL_CreateRGBSurfaceWithFormat(Uint32 flags, int w, int h, int depth, Uint32 format);
void SDL_FreeSurface(SDL_Surface *surface);
int SDL_SetSurfaceBlendMode(SDL_Surface *surface, SDL_BlendMode blend);
int SDL_BlitScaled(SDL_Surface *src, const SDL_Rect *srcrect, SDL_Surface *dst,
                   SDL_Rect *dstrect);
int SDL_SaveBMP(SDL_Surface *surface, const char *file);

SDL_Texture *SDL_CreateTextureFromSurface(SDL_Renderer *renderer, SDL_Surface *surface);
void SDL_DestroyTexture(SDL_Texture *texture);
int SDL_SetTextureBlendMode(SDL_Texture *texture, SDL_BlendMode blend);
int SDL_SetTextureAlphaMod(SDL_Texture *texture, Uint8 alpha);

Uint32 SDL_GetTicks(void);
int SDL_PollEvent(SDL_Event *event);

int SDL_NumJoysticks(void);
SDL_bool SDL_IsGameController(int joystick_index);
SDL_GameController *SDL_GameControllerOpen(int joystick_index);
void SDL_GameControllerClose(SDL_GameController *controller);
SDL_Joystick *SDL_GameControllerGetJoystick(SDL_GameController *controller);
SDL_JoystickID SDL_JoystickInstanceID(SDL_Joystick *joystick);

#endif /* CLASS09_SDL_COMPAT_H */
