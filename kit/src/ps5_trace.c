/*
 * Lightweight boot tracing and fatal-signal logging for the PS5 build.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#ifndef _XOPEN_SOURCE
#define _XOPEN_SOURCE 700
#endif

#include "ps5_trace.h"

#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ucontext.h>
#include <unistd.h>

/* Present on retail kernels; weak so a missing export cannot break the load. */
extern int sceKernelDebugOutText(int channel, const char *text) __attribute__((weak));

static int g_trace_fd = -1;
static int g_trace_fd_shared = -1;
static volatile sig_atomic_t g_in_handler = 0;

static void fd_write_all(int fd, const char *text, size_t length) {
    size_t done = 0;
    while (fd >= 0 && done < length) {
        ssize_t n = write(fd, text + done, length - done);
        if (n <= 0) {
            break;
        }
        done += (size_t)n;
    }
}

static void raw_emit(const char *text, size_t length) {
    fd_write_all(g_trace_fd, text, length);
    fd_write_all(g_trace_fd_shared, text, length);
    if (sceKernelDebugOutText) {
        char chunk[256];
        size_t at = 0;
        while (at < length) {
            size_t take = length - at;
            if (take > sizeof(chunk) - 1) {
                take = sizeof(chunk) - 1;
            }
            memcpy(chunk, text + at, take);
            chunk[take] = '\0';
            sceKernelDebugOutText(0, chunk);
            at += take;
        }
    }
}

void c09_trace(const char *fmt, ...) {
    char buffer[512];
    va_list args;
    int written;

    va_start(args, fmt);
    written = vsnprintf(buffer, sizeof(buffer) - 2, fmt, args);
    va_end(args);
    if (written < 0) {
        return;
    }
    if ((size_t)written > sizeof(buffer) - 2) {
        written = (int)(sizeof(buffer) - 2);
    }
    buffer[written++] = '\n';
    buffer[written] = '\0';
    raw_emit(buffer, (size_t)written);
}

static size_t append_hex(char *out, uint64_t value) {
    static const char digits[] = "0123456789abcdef";
    char tmp[18];
    size_t n = 0;
    size_t i;
    do {
        tmp[n++] = digits[value & 0xf];
        value >>= 4;
    } while (value);
    for (i = 0; i < n; i++) {
        out[i] = tmp[n - 1 - i];
    }
    return n;
}

static size_t append_dec(char *out, long value) {
    char tmp[24];
    size_t n = 0;
    size_t i;
    unsigned long v = value < 0 ? (unsigned long)(-value) : (unsigned long)value;
    do {
        tmp[n++] = (char)('0' + (v % 10));
        v /= 10;
    } while (v);
    i = 0;
    if (value < 0) {
        out[i++] = '-';
    }
    while (n) {
        out[i++] = tmp[--n];
    }
    return i;
}

static void fatal_signal(int sig, siginfo_t *info, void *context) {
    char line[512];
    size_t at = 0;
    ucontext_t *uc = (ucontext_t *)context;
    int i;

    if (g_in_handler) {
        _exit(128 + sig);
    }
    g_in_handler = 1;

    memcpy(line, "FATAL sig=", 10);
    at = 10;
    at += append_dec(line + at, sig);
    memcpy(line + at, " code=", 6);
    at += 6;
    at += append_dec(line + at, info ? info->si_code : -1);
    if (info) {
        line[at++] = ' ';
        line[at++] = 'a';
        line[at++] = 'd';
        line[at++] = 'd';
        line[at++] = 'r';
        line[at++] = '=';
        line[at++] = '0';
        line[at++] = 'x';
        at += append_hex(line + at, (uint64_t)(uintptr_t)info->si_addr);
    }
    if (uc) {
        static const char *names[] = {"rip", "rsp", "rbp", "rax", "rbx", "rdi", "rsi", "rdx",
                                      "rcx", "r8 ", "r9 ", "r10", "r11", "r12", "r13", "r14",
                                      "r15"};
        uint64_t values[] = {uc->uc_mcontext.mc_rip, uc->uc_mcontext.mc_rsp, uc->uc_mcontext.mc_rbp,
                             uc->uc_mcontext.mc_rax, uc->uc_mcontext.mc_rbx, uc->uc_mcontext.mc_rdi,
                             uc->uc_mcontext.mc_rsi, uc->uc_mcontext.mc_rdx, uc->uc_mcontext.mc_rcx,
                             uc->uc_mcontext.mc_r8,  uc->uc_mcontext.mc_r9,  uc->uc_mcontext.mc_r10,
                             uc->uc_mcontext.mc_r11, uc->uc_mcontext.mc_r12, uc->uc_mcontext.mc_r13,
                             uc->uc_mcontext.mc_r14, uc->uc_mcontext.mc_r15};
        for (i = 0; i < (int)(sizeof(values) / sizeof(values[0])); i++) {
            line[at++] = ' ';
            memcpy(line + at, names[i], 3);
            at += 3;
            line[at++] = '=';
            line[at++] = '0';
            line[at++] = 'x';
            at += append_hex(line + at, values[i]);
            if (at > sizeof(line) - 32) {
                break;
            }
        }
        /* A few stack words often reveal the syscall number and arguments. */
        for (i = 0; i < 8 && at < sizeof(line) - 24; i++) {
            uint64_t word = 0;
            memcpy(&word, (const void *)(uintptr_t)(uc->uc_mcontext.mc_rsp + (uint64_t)i * 8),
                   sizeof(word));
            line[at++] = ' ';
            line[at++] = 's';
            line[at++] = (char)('0' + i);
            line[at++] = '=';
            line[at++] = '0';
            line[at++] = 'x';
            at += append_hex(line + at, word);
        }
        /* Absolute addresses of known functions: base = value - static offset. */
        line[at++] = ' ';
        memcpy(line + at, "tracefn=0x", 10);
        at += 10;
        at += append_hex(line + at, (uint64_t)(uintptr_t)&c09_trace);
        line[at++] = ' ';
        memcpy(line + at, "initfn=0x", 9);
        at += 9;
        at += append_hex(line + at, (uint64_t)(uintptr_t)&c09_trace_init);
    }
    line[at++] = '\n';
    raw_emit(line, at);

    /* Fall through to the default action so the system sees the crash. */
    signal(sig, SIG_DFL);
    raise(sig);
}

void c09_write_bmp(const char *path, const void *pixels, int width, int height) {
    static unsigned char header[54];
    unsigned char *row;
    int fd;
    int y;
    int row_bytes;
    int stride;
    unsigned long file_size;

    if (!path || !pixels || width <= 0 || height <= 0) {
        return;
    }
    row_bytes = width * 3;
    stride = (row_bytes + 3) & ~3;
    file_size = 54ul + (unsigned long)stride * (unsigned long)height;
    row = (unsigned char *)malloc((size_t)stride);
    if (!row) {
        return;
    }
    memset(header, 0, sizeof(header));
    header[0] = 'B';
    header[1] = 'M';
    header[2] = (unsigned char)(file_size);
    header[3] = (unsigned char)(file_size >> 8);
    header[4] = (unsigned char)(file_size >> 16);
    header[5] = (unsigned char)(file_size >> 24);
    header[10] = 54;
    header[14] = 40;
    header[18] = (unsigned char)(width);
    header[19] = (unsigned char)(width >> 8);
    header[20] = (unsigned char)(width >> 16);
    header[21] = (unsigned char)(width >> 24);
    header[22] = (unsigned char)(height);
    header[23] = (unsigned char)(height >> 8);
    header[24] = (unsigned char)(height >> 16);
    header[25] = (unsigned char)(height >> 24);
    header[26] = 1;
    header[28] = 24;
    header[34] = (unsigned char)(stride * height);
    header[35] = (unsigned char)((stride * height) >> 8);
    header[36] = (unsigned char)((stride * height) >> 16);
    header[37] = (unsigned char)((stride * height) >> 24);
    header[38] = 0x13;
    header[39] = 0x0b;
    header[42] = 0x13;
    header[43] = 0x0b;

    fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0777);
    if (fd < 0) {
        free(row);
        return;
    }
    fd_write_all(fd, (const char *)header, sizeof(header));
    for (y = height - 1; y >= 0; y--) {
        const unsigned char *src = (const unsigned char *)pixels + (size_t)y * (size_t)width * 4u;
        int x;
        for (x = 0; x < width; x++) {
            /* Source pixels are RGBA bytes; BMP stores BGR. */
            row[x * 3 + 0] = src[x * 4 + 2];
            row[x * 3 + 1] = src[x * 4 + 1];
            row[x * 3 + 2] = src[x * 4 + 0];
        }
        for (x = row_bytes; x < stride; x++) {
            row[x] = 0;
        }
        fd_write_all(fd, (const char *)row, (size_t)stride);
    }
    close(fd);
    free(row);
}

void c09_trace_init(void) {
    struct sigaction action;
    static const int fatal[] = {SIGSYS, SIGSEGV, SIGBUS, SIGILL, SIGABRT, SIGFPE, SIGTRAP};
    size_t i;

    if (g_trace_fd < 0) {
        g_trace_fd = open("/download0/c09trace.txt", O_WRONLY | O_CREAT | O_APPEND, 0777);
    }
    if (g_trace_fd_shared < 0) {
        g_trace_fd_shared = open("/data/c09trace.txt", O_WRONLY | O_CREAT | O_APPEND, 0777);
    }

    memset(&action, 0, sizeof(action));
    action.sa_sigaction = fatal_signal;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    for (i = 0; i < sizeof(fatal) / sizeof(fatal[0]); i++) {
        sigaction(fatal[i], &action, NULL);
    }

    c09_trace("trace: init pid=%d fd=%d shared=%d tracefn=%p initfn=%p", (int)getpid(), g_trace_fd,
              g_trace_fd_shared, (void *)&c09_trace, (void *)&c09_trace_init);
}

__attribute__((constructor(101))) static void c09_trace_ctor(void) { c09_trace_init(); }
