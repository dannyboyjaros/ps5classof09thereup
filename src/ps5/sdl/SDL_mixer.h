/*
 * Minimal SDL_mixer surface for the Class of '09 PS5 runtime.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef CLASS09_SDL_MIXER_COMPAT_H
#define CLASS09_SDL_MIXER_COMPAT_H

#include "SDL.h"

#define MIX_MAX_VOLUME 128
#define MIX_DEFAULT_FORMAT 0x8010 /* AUDIO_S16LSB */

enum { MIX_INIT_OGG = 0x00000001, MIX_INIT_MP3 = 0x00000008 };

typedef struct Mix_Audio {
    Sint16 *pcm;  /* interleaved stereo at `rate` */
    int frames;   /* sample frames */
    int rate;     /* source sample rate */
    Uint8 volume; /* 0..128 */
    int allocated;
} Mix_Audio;

typedef Mix_Audio Mix_Chunk;
typedef Mix_Audio Mix_Music;

int Mix_Init(int flags);
void Mix_Quit(void);
int Mix_OpenAudio(int frequency, Uint16 format, int channels, int chunksize);
void Mix_CloseAudio(void);
int Mix_AllocateChannels(int numchannels);

Mix_Chunk *Mix_LoadWAV(const char *file);
void Mix_FreeChunk(Mix_Chunk *chunk);
Mix_Music *Mix_LoadMUS(const char *file);
void Mix_FreeMusic(Mix_Music *music);

int Mix_PlayChannel(int channel, Mix_Chunk *chunk, int loops);
int Mix_FadeInChannel(int channel, Mix_Chunk *chunk, int loops, int ms);
int Mix_HaltChannel(int channel);
int Mix_FadeOutChannel(int channel, int ms);
int Mix_Volume(int channel, int volume);
void Mix_Pause(int channel);
void Mix_Resume(int channel);

int Mix_PlayMusic(Mix_Music *music, int loops);
int Mix_HaltMusic(void);
void Mix_PauseMusic(void);
void Mix_ResumeMusic(void);
int Mix_VolumeMusic(int volume);
int Mix_SetMusicPosition(double position);

const char *Mix_GetError(void);

#endif
