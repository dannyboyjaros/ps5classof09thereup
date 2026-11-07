/*
 * Audio for the PS5 runtime: MP3/WAV decoding plus a small software mixer
 * feeding the PS5's AudioOut.
 *
 * engine.c's audio model is: channels 0/1 are looping ambient/music beds,
 * channel 2 is the UI effect, and the single "music" stream is the dialogue
 * voice. That maps onto eight mixer channels and one voice stream here.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "SDL.h"
#include "SDL_mixer.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MINIMP3_IMPLEMENTATION
#include "minimp3_ex.h"

extern int sceAudioOutInit(void);
extern int sceAudioOutOpen(int user, int type, int index, unsigned grain, unsigned rate,
                           unsigned format);
extern int sceAudioOutOutput(int handle, const void *samples);

#define OUT_RATE 48000
#define GRAIN 256
#define MAX_CHANNELS 8

typedef struct {
    Mix_Chunk *chunk;
    int playing;
    int paused;
    int loops; /* -1 = forever */
    int volume; /* 0..128 */
    double pos; /* source frame position */
    double step; /* source frames per output frame */
    int fade_remaining; /* output frames left in the current fade-in */
    int fade_length;
    int fading_out;
} Channel;

static Channel g_channels[MAX_CHANNELS];
static Mix_Chunk *g_voice;
static int g_voice_playing;
static double g_voice_pos;
static int g_voice_volume = MIX_MAX_VOLUME;
static int g_music_paused;

static int g_audio_handle = -1;
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static char g_mix_error[128] = "";

static int g_open;

const char *Mix_GetError(void) { return g_mix_error; }

/* ------------------------------------------------------------------------- */
/* decoding                                                                  */
/* ------------------------------------------------------------------------- */
static int decode_wav(const unsigned char *data, size_t size, Mix_Audio *out) {
    const unsigned char *p;
    size_t remaining;
    int channels = 0, rate = 0, bits = 0;
    size_t data_offset = 0, data_size = 0;

    if (size < 12 || memcmp(data, "RIFF", 4) != 0 || memcmp(data + 8, "WAVE", 4) != 0) {
        return 0;
    }

    p = data + 12;
    remaining = size - 12;
    while (remaining >= 8) {
        unsigned chunk_size = (unsigned)p[4] | ((unsigned)p[5] << 8) | ((unsigned)p[6] << 16) |
                              ((unsigned)p[7] << 24);
        if (memcmp(p, "fmt ", 4) == 0 && chunk_size >= 16 && remaining >= chunk_size + 8) {
            channels = p[10] | (p[11] << 8);
            rate = p[12] | (p[13] << 8) | (p[14] << 16) | (p[15] << 24);
            bits = p[22] | (p[23] << 8);
        } else if (memcmp(p, "data", 4) == 0) {
            data_offset = 8;
            data_size = chunk_size;
            if (data_size > remaining - 8) data_size = remaining - 8;
            break;
        }
        if (chunk_size == 0 || chunk_size > remaining - 8) break;
        p += 8 + chunk_size;
        remaining -= 8 + chunk_size;
    }

    if (!channels || !rate || bits != 16 || !data_size) return 0;

    out->frames = (int)(data_size / (size_t)(channels * 2));
    out->rate = rate;
    out->pcm = (Sint16 *)malloc((size_t)out->frames * 2u * sizeof(Sint16));
    if (!out->pcm) return 0;
    out->allocated = 1;
    out->volume = MIX_MAX_VOLUME;

    {
        const Sint16 *src = (const Sint16 *)(data + data_offset);
        int i;
        for (i = 0; i < out->frames; i++) {
            if (channels >= 2) {
                out->pcm[i * 2 + 0] = src[i * channels + 0];
                out->pcm[i * 2 + 1] = src[i * channels + 1];
            } else {
                out->pcm[i * 2 + 0] = src[i];
                out->pcm[i * 2 + 1] = src[i];
            }
        }
    }
    return 1;
}

static int decode_mp3(const char *file, Mix_Audio *out) {
    mp3dec_t decoder;
    mp3dec_file_info_t info;
    int result;
    int i;

    memset(&info, 0, sizeof(info));
    mp3dec_init(&decoder);
    result = mp3dec_load(&decoder, file, &info, NULL, NULL);
    if (result != 0 || !info.buffer || info.samples == 0) {
        snprintf(g_mix_error, sizeof(g_mix_error), "MP3 decode failed (%d)", result);
        free(info.buffer);
        return 0;
    }

    if (info.channels == 1) {
        size_t frames = info.samples;
        out->pcm = (Sint16 *)malloc(frames * 2u * sizeof(Sint16));
        if (!out->pcm) {
            free(info.buffer);
            return 0;
        }
        for (i = 0; i < (int)frames; i++) {
            out->pcm[i * 2 + 0] = info.buffer[i];
            out->pcm[i * 2 + 1] = info.buffer[i];
        }
        out->frames = (int)frames;
    } else {
        out->pcm = (Sint16 *)info.buffer;
        out->frames = (int)(info.samples / (size_t)info.channels);
    }
    out->rate = info.hz > 0 ? info.hz : 44100;
    out->allocated = 1;
    out->volume = MIX_MAX_VOLUME;
    return 1;
}

static Mix_Audio *load_audio(const char *file) {
    FILE *f;
    long size;
    unsigned char *data;
    Mix_Audio *audio;

    if (!file) return NULL;
    f = fopen(file, "rb");
    if (!f) {
        snprintf(g_mix_error, sizeof(g_mix_error), "cannot open %s", file);
        return NULL;
    }
    fseek(f, 0, SEEK_END);
    size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size <= 0) {
        fclose(f);
        return NULL;
    }
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

    audio = (Mix_Audio *)calloc(1, sizeof(Mix_Audio));
    if (!audio) {
        free(data);
        return NULL;
    }

    if (!decode_wav(data, (size_t)size, audio)) {
        if (!decode_mp3(file, audio)) {
            free(audio);
            free(data);
            return NULL;
        }
    }
    free(data);
    return audio;
}

/* ------------------------------------------------------------------------- */
/* mixer                                                                     */
/* ------------------------------------------------------------------------- */
static double channel_step(const Mix_Audio *audio) {
    if (!audio || audio->rate <= 0) return 1.0;
    return (double)audio->rate / (double)OUT_RATE;
}

static float read_source(const Mix_Audio *audio, double pos, int channel) {
    int i0 = (int)pos;
    int i1 = i0 + 1;
    double frac = pos - (double)i0;
    float a, b;
    if (!audio->pcm || i0 < 0 || i0 >= audio->frames) return 0.0f;
    if (i1 >= audio->frames) i1 = audio->frames - 1;
    a = (float)audio->pcm[i0 * 2 + channel];
    b = (float)audio->pcm[i1 * 2 + channel];
    return a + (b - a) * (float)frac;
}

static void render_frames(Sint16 *out, int frames) {
    int i, c;
    static float left[GRAIN];
    static float right[GRAIN];
    float master = (float)g_voice_volume / (float)MIX_MAX_VOLUME;

    memset(left, 0, sizeof(float) * (size_t)frames);
    memset(right, 0, sizeof(float) * (size_t)frames);

    pthread_mutex_lock(&g_lock);

    for (c = 0; c < MAX_CHANNELS; c++) {
        Channel *ch = &g_channels[c];
        int n;
        if (!ch->playing || !ch->chunk || ch->paused) continue;
        for (n = 0; n < frames; n++) {
            float gain = (float)ch->volume / (float)MIX_MAX_VOLUME;
            if (ch->fading_out) {
                if (ch->fade_length > 0) {
                    float left = (float)ch->fade_remaining / (float)ch->fade_length;
                    if (left < 0.0f) left = 0.0f;
                    gain *= left;
                }
                if (--ch->fade_remaining <= 0) {
                    ch->playing = 0;
                    break;
                }
            } else if (ch->fade_remaining > 0 && ch->fade_length > 0) {
                float done = (float)(ch->fade_length - ch->fade_remaining) /
                             (float)ch->fade_length;
                gain *= done;
                ch->fade_remaining--;
            }
            if (ch->pos >= (double)ch->chunk->frames) {
                if (ch->loops < 0 || ch->loops > 0) {
                    if (ch->loops > 0) ch->loops--;
                    ch->pos = 0.0;
                } else {
                    ch->playing = 0;
                    break;
                }
            }
            left[n] += read_source(ch->chunk, ch->pos, 0) * gain;
            right[n] += read_source(ch->chunk, ch->pos, 1) * gain;
            ch->pos += ch->step;
        }
    }

    if (g_voice_playing && g_voice && !g_music_paused) {
        int n;
        for (n = 0; n < frames; n++) {
            if (g_voice_pos >= (double)g_voice->frames) {
                g_voice_playing = 0;
                break;
            }
            left[n] += read_source(g_voice, g_voice_pos, 0) * master;
            right[n] += read_source(g_voice, g_voice_pos, 1) * master;
            g_voice_pos += channel_step(g_voice);
        }
    }

    pthread_mutex_unlock(&g_lock);

    for (i = 0; i < frames; i++) {
        float l = left[i];
        float r = right[i];
        if (l > 32767.0f) l = 32767.0f;
        if (l < -32768.0f) l = -32768.0f;
        if (r > 32767.0f) r = 32767.0f;
        if (r < -32768.0f) r = -32768.0f;
        out[i * 2 + 0] = (Sint16)l;
        out[i * 2 + 1] = (Sint16)r;
    }
}

static void *audio_thread(void *unused) {
    static Sint16 samples[GRAIN * 2];
    (void)unused;
    for (;;) {
        render_frames(samples, GRAIN);
        if (sceAudioOutOutput(g_audio_handle, samples) < 0) {
            break;
        }
    }
    return NULL;
}

/* ------------------------------------------------------------------------- */
/* SDL_mixer API                                                             */
/* ------------------------------------------------------------------------- */
int Mix_Init(int flags) { return flags; }

void Mix_Quit(void) {}

int Mix_OpenAudio(int frequency, Uint16 format, int channels, int chunksize) {
    int r;
    pthread_t thread;
    (void)frequency;
    (void)format;
    (void)channels;
    (void)chunksize;

    if (g_open) return 0;

    r = sceAudioOutInit();
    if (r != 0 && (unsigned)r != 0x8026000eu) {
        g_audio_handle = -1;
    } else {
        g_audio_handle = sceAudioOutOpen(0xff, 0, 0, GRAIN, OUT_RATE, 1);
    }
    if (g_audio_handle < 0) {
        snprintf(g_mix_error, sizeof(g_mix_error), "sceAudioOutOpen failed (%d)", g_audio_handle);
        return -1;
    }

    memset(g_channels, 0, sizeof(g_channels));
    {
        int i;
        for (i = 0; i < MAX_CHANNELS; i++) {
            g_channels[i].volume = MIX_MAX_VOLUME;
        }
    }

    if (pthread_create(&thread, NULL, audio_thread, NULL) != 0) {
        snprintf(g_mix_error, sizeof(g_mix_error), "cannot start the audio thread");
        return -1;
    }
    pthread_detach(thread);
    g_open = 1;
    return 0;
}

void Mix_CloseAudio(void) {
    g_open = 0;
    g_audio_handle = -1;
}

int Mix_AllocateChannels(int numchannels) {
    (void)numchannels;
    return MAX_CHANNELS;
}

Mix_Chunk *Mix_LoadWAV(const char *file) { return load_audio(file); }

void Mix_FreeChunk(Mix_Chunk *chunk) {
    if (!chunk) return;
    {
        int i;
        pthread_mutex_lock(&g_lock);
        for (i = 0; i < MAX_CHANNELS; i++) {
            if (g_channels[i].chunk == chunk) {
                g_channels[i].playing = 0;
                g_channels[i].chunk = NULL;
            }
        }
        pthread_mutex_unlock(&g_lock);
    }
    free(chunk->pcm);
    free(chunk);
}

Mix_Music *Mix_LoadMUS(const char *file) { return load_audio(file); }

void Mix_FreeMusic(Mix_Music *music) {
    if (!music) return;
    pthread_mutex_lock(&g_lock);
    if (g_voice == music) {
        g_voice = NULL;
        g_voice_playing = 0;
    }
    pthread_mutex_unlock(&g_lock);
    free(music->pcm);
    free(music);
}

static int start_channel(int channel, Mix_Chunk *chunk, int loops, int fade_ms) {
    if (channel < 0 || channel >= MAX_CHANNELS || !chunk || !chunk->pcm) return -1;
    pthread_mutex_lock(&g_lock);
    g_channels[channel].chunk = chunk;
    g_channels[channel].playing = 1;
    g_channels[channel].loops = loops;
    g_channels[channel].pos = 0.0;
    g_channels[channel].step = channel_step(chunk);
    g_channels[channel].fading_out = 0;
    g_channels[channel].paused = 0;
    g_channels[channel].fade_length = fade_ms * OUT_RATE / 1000;
    g_channels[channel].fade_remaining = fade_ms > 0 ? (g_channels[channel].fade_length) : 0;
    pthread_mutex_unlock(&g_lock);
    return channel;
}

int Mix_PlayChannel(int channel, Mix_Chunk *chunk, int loops) {
    return start_channel(channel, chunk, loops, 0);
}

int Mix_FadeInChannel(int channel, Mix_Chunk *chunk, int loops, int ms) {
    return start_channel(channel, chunk, loops, ms > 0 ? ms : 0);
}

int Mix_HaltChannel(int channel) {
    if (channel < 0) {
        int i;
        pthread_mutex_lock(&g_lock);
        for (i = 0; i < MAX_CHANNELS; i++) g_channels[i].playing = 0;
        pthread_mutex_unlock(&g_lock);
        return 0;
    }
    if (channel < MAX_CHANNELS) {
        pthread_mutex_lock(&g_lock);
        g_channels[channel].playing = 0;
        pthread_mutex_unlock(&g_lock);
    }
    return 0;
}

int Mix_FadeOutChannel(int channel, int ms) {
    if (channel < 0 || channel >= MAX_CHANNELS) return -1;
    pthread_mutex_lock(&g_lock);
    if (g_channels[channel].playing) {
        g_channels[channel].fading_out = 1;
        g_channels[channel].fade_length = ms > 0 ? ms * OUT_RATE / 1000 : 1;
        g_channels[channel].fade_remaining = g_channels[channel].fade_length;
    }
    pthread_mutex_unlock(&g_lock);
    return 0;
}

int Mix_Volume(int channel, int volume) {
    if (volume < 0) volume = 0;
    if (volume > MIX_MAX_VOLUME) volume = MIX_MAX_VOLUME;
    pthread_mutex_lock(&g_lock);
    if (channel < 0) {
        int i;
        for (i = 0; i < MAX_CHANNELS; i++) g_channels[i].volume = volume;
    } else if (channel < MAX_CHANNELS) {
        g_channels[channel].volume = volume;
    }
    pthread_mutex_unlock(&g_lock);
    return volume;
}

void Mix_Pause(int channel) {
    if (channel < 0) {
        int i;
        pthread_mutex_lock(&g_lock);
        for (i = 0; i < MAX_CHANNELS; i++) {
            if (g_channels[i].playing) g_channels[i].paused = 1;
        }
        pthread_mutex_unlock(&g_lock);
        return;
    }
    if (channel < MAX_CHANNELS) {
        pthread_mutex_lock(&g_lock);
        g_channels[channel].paused = 1;
        pthread_mutex_unlock(&g_lock);
    }
}

void Mix_Resume(int channel) {
    if (channel < 0) {
        int i;
        pthread_mutex_lock(&g_lock);
        for (i = 0; i < MAX_CHANNELS; i++) {
            g_channels[i].paused = 0;
        }
        pthread_mutex_unlock(&g_lock);
        return;
    }
    if (channel < MAX_CHANNELS) {
        pthread_mutex_lock(&g_lock);
        g_channels[channel].paused = 0;
        pthread_mutex_unlock(&g_lock);
    }
}

int Mix_PlayMusic(Mix_Music *music, int loops) {
    (void)loops;
    if (!music || !music->pcm) return -1;
    pthread_mutex_lock(&g_lock);
    g_voice = music;
    g_voice_pos = 0.0;
    g_voice_playing = 1;
    g_music_paused = 0;
    pthread_mutex_unlock(&g_lock);
    return 0;
}

int Mix_HaltMusic(void) {
    pthread_mutex_lock(&g_lock);
    g_voice_playing = 0;
    pthread_mutex_unlock(&g_lock);
    return 0;
}

void Mix_PauseMusic(void) {
    g_music_paused = 1;
}

void Mix_ResumeMusic(void) {
    g_music_paused = 0;
}

int Mix_VolumeMusic(int volume) {
    if (volume < 0) volume = 0;
    if (volume > MIX_MAX_VOLUME) volume = MIX_MAX_VOLUME;
    g_voice_volume = volume;
    return volume;
}

int Mix_SetMusicPosition(double position) {
    pthread_mutex_lock(&g_lock);
    if (g_voice) {
        g_voice_pos = position * (double)g_voice->rate;
        if (g_voice_pos < 0) g_voice_pos = 0;
    }
    pthread_mutex_unlock(&g_lock);
    return 0;
}
