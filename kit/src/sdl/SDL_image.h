/*
 * Minimal SDL_image surface for the Class of '09 PS5 runtime.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef CLASS09_SDL_IMAGE_COMPAT_H
#define CLASS09_SDL_IMAGE_COMPAT_H

#include "SDL.h"

enum { IMG_INIT_JPG = 0x00000001, IMG_INIT_PNG = 0x00000002 };

int IMG_Init(int flags);
void IMG_Quit(void);
SDL_Surface *IMG_Load(const char *file);
const char *IMG_GetError(void);

#endif
