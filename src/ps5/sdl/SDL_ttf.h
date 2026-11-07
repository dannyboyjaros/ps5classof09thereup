/*
 * Minimal SDL_ttf surface for the Class of '09 PS5 runtime.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef CLASS09_SDL_TTF_COMPAT_H
#define CLASS09_SDL_TTF_COMPAT_H

#include "SDL.h"

typedef struct TTF_Font TTF_Font;

int TTF_Init(void);
void TTF_Quit(void);
TTF_Font *TTF_OpenFont(const char *file, int ptsize);
void TTF_CloseFont(TTF_Font *font);
int TTF_FontLineSkip(const TTF_Font *font);
int TTF_SizeUTF8(TTF_Font *font, const char *text, int *w, int *h);
SDL_Surface *TTF_RenderUTF8_Blended(TTF_Font *font, const char *text, SDL_Color color);
const char *TTF_GetError(void);

#endif
