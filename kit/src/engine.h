#ifndef ENGINE_H
#define ENGINE_H

#include "json_lite.h"

#include <SDL.h>
#include <SDL_image.h>
#include <SDL_mixer.h>
#include <SDL_ttf.h>

/* The game is authored for a 1920x1080 virtual screen. */
#define SCREEN_W 1920
#define SCREEN_H 1080

#define MAX_ITEMS 96
#define MAX_CHOICES 16
#define CALL_STACK 64
#define MAX_TEXT 4096
#define MAX_PATH 512
#define SAVE_PATH_MAX (MAX_PATH + 32)
#define SPLASH_PATH_MAX (SAVE_PATH_MAX + MAX_PATH)
#define MAX_LINES 40
#define TEXT_CACHE 48
#define TEX_CACHE 64
#define CHUNK_CACHE 32
#define MAX_SLOTS 36
#define MAX_ANIM 8
#define MAX_SEEN 64
#define MAX_TOAST 256

/* Font slots.  Every slot has a path and a pixel size from the game GUI. */
enum {
    FONT_DIALOGUE = 0,
    FONT_NAME,
    FONT_CHOICE,
    FONT_MENU,
    FONT_SMALL,
    FONT_TITLE,
    FONT_BODY,
    FONT_SLOT,
    FONT_CSBOX,
    FONT_TRACKER,
    FONT_COUNT
};

/* Top-level screens. */
enum {
    MODE_MENU = 0,
    MODE_GAME,
    MODE_PAUSE,
    MODE_SAVE,
    MODE_LOAD,
    MODE_OPTIONS,
    MODE_ABOUT,
    MODE_TRACKER
};

/* Why the interpreter is waiting for input or a timer. */
enum {
    WAIT_NONE = 0,
    WAIT_SAY,
    WAIT_PAUSE,
    WAIT_MENU,
    WAIT_MOVIE,
    WAIT_ENDING,
    WAIT_LAPTOP
};

typedef struct {
    char path[MAX_PATH];
    SDL_Texture *tex;
    int w;
    int h;
    int refs;
    Uint32 last_used;
} TexEntry;

typedef struct {
    char path[MAX_PATH];
    Mix_Chunk *chunk;
} ChunkEntry;

typedef struct {
    int used;
    int font;
    int wrap;
    Uint32 color;
    char text[MAX_TEXT];
    int line_count;
    char lines[MAX_LINES][512];
    SDL_Texture *tex[MAX_LINES];
    int tw[MAX_LINES];
    int th[MAX_LINES];
    Uint32 last_used;
} TextBlock;

typedef struct {
    int used;
    char tag[64];
    char layer[16];
    char kind[16];
    char rel[MAX_PATH];
    char arg[64];
    int x;
    int y;
    int w;
    int h;
    int alpha; /* 0..255 */
    int flip;
    int order;

    /* ATL keyframes: [time_ms, x, y, w, h, alpha, flip].  The final
     * geometry above is used when animation is absent or finished. */
    int anim_count;
    int anim[MAX_ANIM][7];
    Uint32 anim_start;
    int anim_paused;
} LayerItem;

/* One remembered line, so Circle can step back through dialogue. */
#define HISTORY_MAX 32

typedef struct {
    int pc;
    int hud;
    int next_order;
    int item_count;
    int ending_active;
    LayerItem items[MAX_ITEMS];
} HistoryEntry;

typedef struct {
    JsonValue *root;
    JsonValue *ops;
    JsonValue *labels;
    JsonValue *gui;
    JsonValue *endings;
    JsonValue *animations;

    int pc;
    int call_stack[CALL_STACK];
    int call_depth;
    int mode;
    int running;

    /* dialogue / interpreter */
    char speaker[128];
    char line[MAX_TEXT];
    int line_shown;
    int waiting;
    int wait_kind;
    int wait_auto;
    Uint32 wait_deadline;
    double line_start;
    double line_end;
    char voice[MAX_PATH];
    int voice_active;
    int audio_ok;

    /* choices */
    int choice_count;
    int choice_index;
    int choice_targets[MAX_CHOICES];
    char choice_text[MAX_CHOICES][512];

    /* staging */
    LayerItem items[MAX_ITEMS];
    int item_count;
    int next_order;
    int hud;
    HistoryEntry history[HISTORY_MAX];
    int history_pos;
    int csbox;                 /* Re-Up cutscene dialogue: yellow, no text box */
    int laptop_active;         /* call screen search_engine_screen */
    char laptop_target[64];
    char start_variant[64];    /* persistent.start_label_jump (A/B opening) */
    int ending_active;
    char ending_title[256];
    char ending_body[MAX_TEXT];

    /* audio paths kept so they survive a save/load */
    char ambient_path[MAX_PATH];
    char music_path[MAX_PATH];
    Mix_Chunk *ambient_chunk;
    Mix_Chunk *music_chunk;
    Mix_Music *voice_music;
    char voice_music_path[MAX_PATH];

    /* caches */
    TexEntry tex_cache[TEX_CACHE];
    int tex_count;
    ChunkEntry chunk_cache[CHUNK_CACHE];
    int chunk_count;
    TextBlock text_cache[TEXT_CACHE];
    int text_count;
    Uint32 frame_counter;

    /* fonts */
    TTF_Font *fonts[FONT_COUNT];
    char font_paths[FONT_COUNT][MAX_PATH];
    int font_sizes[FONT_COUNT];

    /* window / renderer */
    SDL_Window *window;
    SDL_Renderer *renderer;
    SDL_GameController *pad;
    char game_dir[MAX_PATH];
    char save_dir[MAX_PATH];
    char data_dir[MAX_PATH];
    char script_path[MAX_PATH];

    /* GUI metrics loaded from script.json */
    char gui_textbox[MAX_PATH];
    char gui_main_menu[MAX_PATH];
    char gui_choice_window[MAX_PATH];
    char gui_choice_idle[MAX_PATH];
    char gui_choice_hover[MAX_PATH];
    char gui_logo[MAX_PATH];
    int gui_logo_x, gui_logo_y, gui_logo_w, gui_logo_h;
    int gui_name_x, gui_name_y;
    Uint32 gui_name_color;
    int gui_dialogue_x, gui_dialogue_y, gui_dialogue_w, gui_dialogue_spacing;
    Uint32 gui_dialogue_color;
    int gui_choice_x, gui_choice_y, gui_choice_w, gui_choice_h, gui_choice_spacing;
    Uint32 gui_choice_idle_color;
    Uint32 gui_choice_hover_color;
    char gui_menu_music[MAX_PATH];

    /* menus */
    int main_index;
    int pause_index;
    int load_index;
    int load_return_mode;
    int save_index;
    int save_return_mode;
    int file_page;
    int file_area; /* 0 = slot grid, 1 = page controls */
    int page_focus;
    int want_thumb;
    int options_index;
    int options_return_mode;
    int opt_music;
    int opt_voice;
    int tracker_index;
    int tracker_text;
    Uint32 pause_started;

    /* startup video frame cache (optional, extracted from the user's copy) */
    int splash_active;
    int splash_frames;
    int splash_fps;
    int splash_w;
    int splash_h;
    Uint32 splash_start;
    char splash_dir[SAVE_PATH_MAX];
    SDL_Texture *splash_tex;
    int splash_tex_index;

    /* video (C09V frame packs + mp3 audio) */
    int video_active;
    int video_mode; /* 0 = movie op, 1 = movie displayable, 2 = boot */
    int video_loop;
    int video_webm;
    char video_name[64];
    void *webm_player;
    int webm_tex_serial;
    unsigned char *video_pack;
    size_t video_pack_size;
    unsigned int *video_offsets;
    int video_w;
    int video_h;
    int video_fps;
    int video_frames;
    SDL_Texture *video_tex;
    int video_tex_index;
    Uint32 video_start;
    Mix_Music *video_music;
    int boot_active;
    int boot_index;

    /* transient status line */
    Uint32 toast_until;
    char toast[MAX_TOAST];
    int shot_requested;
    Uint32 capture_at;

    /* persistent ending tracker */
    int seen_count;
    char seen[MAX_SEEN][8];
} Engine;

int engine_init(Engine *engine, const char *script_path, const char *game_dir);
void engine_shutdown(Engine *engine);
int engine_frame(Engine *engine);

#endif
