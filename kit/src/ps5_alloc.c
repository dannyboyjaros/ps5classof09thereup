/*
 * Direct-memory heap for the Class of '09 PS5 runtime.
 *
 * The native app process starts with a small platform libc heap (about 8 MiB),
 * which is not enough for the decoded textures and audio of a 400 MB asset
 * set. The application-side malloc/free/posix_memalign are replaced with a
 * first-fit allocator backed by PS5 direct memory (write-back, CPU only).
 *
 * Layout: every block starts with a 48-byte header. The pointer returned to
 * the caller is header + 48, so it is 16-byte aligned. The block pointer is
 * mirrored in the last 8 bytes of the header (user - 8), which also makes
 * over-aligned allocations recoverable.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifdef __PROSPERO__

#include "ps5_trace.h"

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Direct memory, declared here and resolved by the SDK import stubs. */
extern size_t sceKernelGetDirectMemorySize(void);
extern int sceKernelAllocateDirectMemory(int64_t search_start, int64_t search_end, size_t length,
                                         size_t alignment, int memory_type,
                                         int64_t *physical_address);
extern int sceKernelMapDirectMemory(void **address, size_t length, int protection, int flags,
                                    int64_t physical_address, size_t alignment);

#define C09_BLOCK_MAGIC 0x43303942u /* "B90C" */
#define C09_HEADER_SIZE 48u
#define C09_MIN_BLOCK (C09_HEADER_SIZE + 16u)
#define C09_CHUNK_SIZE (64u * 1024u * 1024u)
#define C09_MAX_TOTAL ((size_t)2u * 1024u * 1024u * 1024u)
#define C09_DMEM_ALIGN (2u * 1024u * 1024u)
#define C09_MEMORY_TYPE_WB_ONION 0
#define C09_PROT_CPU_READ_WRITE 0x03

typedef struct C09Block {
    uint64_t size; /* whole block, header included */
    struct C09Block *prev;
    struct C09Block *next;
    uint32_t is_free;
    uint32_t magic;
    uint64_t reserved;
    struct C09Block *self;
} C09Block;

typedef struct C09FreeLinks {
    C09Block *next;
    C09Block *prev;
} C09FreeLinks;

static C09Block *g_free_head;
static size_t g_mapped_total;
static volatile int g_lock;

static void c09_lock(void) {
    while (__sync_lock_test_and_set(&g_lock, 1)) {
    }
}

static void c09_unlock(void) {
    __sync_lock_release(&g_lock);
}

static uintptr_t c09_align_up(uintptr_t value, size_t alignment) {
    return (value + (uintptr_t)alignment - 1u) & ~((uintptr_t)alignment - 1u);
}

static C09FreeLinks *c09_links(C09Block *block) {
    return (C09FreeLinks *)((uint8_t *)block + C09_HEADER_SIZE);
}

static void c09_insert_free(C09Block *block) {
    C09FreeLinks *links = c09_links(block);
    links->prev = NULL;
    links->next = g_free_head;
    if (g_free_head) {
        c09_links(g_free_head)->prev = block;
    }
    g_free_head = block;
    block->is_free = 1;
}

static void c09_remove_free(C09Block *block) {
    C09FreeLinks *links = c09_links(block);
    if (links->prev) {
        c09_links(links->prev)->next = links->next;
    } else {
        g_free_head = links->next;
    }
    if (links->next) {
        c09_links(links->next)->prev = links->prev;
    }
    links->prev = NULL;
    links->next = NULL;
    block->is_free = 0;
}

static C09Block *c09_grow(size_t need) {
    size_t length = C09_CHUNK_SIZE;
    size_t pool;
    int64_t physical = 0;
    void *address = NULL;
    C09Block *block;
    int result;

    if (need > length) {
        length = (need + C09_DMEM_ALIGN - 1u) & ~(size_t)(C09_DMEM_ALIGN - 1u);
    }
    if (length > C09_MAX_TOTAL || g_mapped_total > C09_MAX_TOTAL - length) {
        c09_trace("alloc: refusing %u MiB, cap reached (%u MiB)", (unsigned)(length >> 20),
                  (unsigned)(g_mapped_total >> 20));
        return NULL;
    }

    pool = sceKernelGetDirectMemorySize();
    result = sceKernelAllocateDirectMemory(0, (int64_t)pool, length, C09_DMEM_ALIGN,
                                           C09_MEMORY_TYPE_WB_ONION, &physical);
    if (result < 0) {
        c09_trace("alloc: direct memory %u MiB failed r=0x%x", (unsigned)(length >> 20),
                  (unsigned)result);
        return NULL;
    }
    result = sceKernelMapDirectMemory(&address, length, C09_PROT_CPU_READ_WRITE, 0, physical,
                                      C09_DMEM_ALIGN);
    if (result < 0 || address == NULL) {
        c09_trace("alloc: map %u MiB failed r=0x%x", (unsigned)(length >> 20), (unsigned)result);
        return NULL;
    }

    /* Fresh direct memory is expected to be zeroed; do it explicitly so code
     * that treats malloc as zeroed (common in ported game code) stays valid. */
    memset(address, 0, length);

    block = (C09Block *)address;
    block->size = (uint64_t)length;
    block->prev = NULL;
    block->next = NULL;
    block->is_free = 1;
    block->magic = C09_BLOCK_MAGIC;
    block->reserved = 0;
    block->self = block;

    g_mapped_total += length;
    c09_insert_free(block);
    c09_trace("alloc: mapped %u MiB at=%p phys=0x%llx total=%u MiB", (unsigned)(length >> 20),
              address, (unsigned long long)physical, (unsigned)(g_mapped_total >> 20));
    return block;
}

static void *c09_allocate(size_t size, size_t alignment) {
    size_t need;
    C09Block *block;
    uint8_t *user;

    if (size == 0) {
        size = 1;
    }
    if (size > (size_t)-1 - C09_HEADER_SIZE - alignment - 16u) {
        return NULL;
    }
    need = C09_HEADER_SIZE + size + 16u;
    if (alignment > 16u) {
        need += alignment;
    }
    need = (need + 15u) & ~(size_t)15u;

    c09_lock();
    block = g_free_head;
    while (block && block->size < need) {
        block = c09_links(block)->next;
    }
    if (!block) {
        block = c09_grow(need);
        if (!block) {
            c09_unlock();
            return NULL;
        }
    }
    c09_remove_free(block);

    if (block->size - need >= C09_MIN_BLOCK) {
        C09Block *rest = (C09Block *)((uint8_t *)block + need);
        rest->size = block->size - need;
        rest->prev = block;
        rest->next = block->next;
        rest->is_free = 1;
        rest->magic = C09_BLOCK_MAGIC;
        rest->reserved = 0;
        rest->self = rest;
        if (rest->next) {
            rest->next->prev = rest;
        }
        block->next = rest;
        block->size = need;
        c09_insert_free(rest);
    }

    block->is_free = 0;
    user = (uint8_t *)block + C09_HEADER_SIZE;
    if (alignment > 16u) {
        user = (uint8_t *)c09_align_up((uintptr_t)user, alignment);
    }
    *(C09Block **)(user - 8) = block;
    c09_unlock();
    return user;
}

void *malloc(size_t size) {
    return c09_allocate(size, 16u);
}

void *calloc(size_t count, size_t size) {
    size_t total;
    void *pointer;

    if (size != 0 && count > (size_t)-1 / size) {
        return NULL;
    }
    total = count * size;
    pointer = c09_allocate(total, 16u);
    if (pointer) {
        memset(pointer, 0, total);
    }
    return pointer;
}

void free(void *pointer) {
    C09Block *block;

    if (!pointer) {
        return;
    }
    block = *(C09Block **)((uint8_t *)pointer - 8);
    if (!block || block->magic != C09_BLOCK_MAGIC || block->self != block ||
        block->is_free) {
        c09_trace("alloc: free of an unknown pointer %p (block=%p)", pointer, (void *)block);
        return;
    }

    c09_lock();
    block->is_free = 1;

    if (block->next && block->next->is_free) {
        C09Block *next = block->next;
        c09_remove_free(next);
        block->size += next->size;
        block->next = next->next;
        if (block->next) {
            block->next->prev = block;
        }
    }
    if (block->prev && block->prev->is_free) {
        C09Block *prev = block->prev;
        c09_remove_free(prev);
        prev->size += block->size;
        prev->next = block->next;
        if (prev->next) {
            prev->next->prev = prev;
        }
        block = prev;
    }
    c09_insert_free(block);
    c09_unlock();
}

void *realloc(void *pointer, size_t size) {
    C09Block *block;
    size_t available;
    void *replacement;
    size_t copy;

    if (!pointer) {
        return c09_allocate(size, 16u);
    }
    if (size == 0) {
        free(pointer);
        return NULL;
    }

    block = *(C09Block **)((uint8_t *)pointer - 8);
    if (!block || block->magic != C09_BLOCK_MAGIC || block->self != block) {
        c09_trace("alloc: realloc of an unknown pointer %p", pointer);
        return NULL;
    }
    available = (size_t)(block->size - (uint64_t)((uint8_t *)pointer - (uint8_t *)block));
    if (size <= available) {
        return pointer;
    }

    replacement = c09_allocate(size, 16u);
    if (!replacement) {
        return NULL;
    }
    copy = available < size ? available : size;
    memcpy(replacement, pointer, copy);
    free(pointer);
    return replacement;
}

int posix_memalign(void **result, size_t alignment, size_t size) {
    void *pointer;

    if (!result) {
        return EINVAL;
    }
    *result = NULL;
    if (alignment < sizeof(void *)) {
        alignment = sizeof(void *);
    }
    if (alignment & (alignment - 1u)) {
        return EINVAL;
    }
    pointer = c09_allocate(size, alignment);
    if (!pointer) {
        return ENOMEM;
    }
    *result = pointer;
    return 0;
}

void *aligned_alloc(size_t alignment, size_t size) {
    if (alignment == 0 || (alignment & (alignment - 1u))) {
        return NULL;
    }
    return c09_allocate(size, alignment < 16u ? 16u : alignment);
}

#endif /* __PROSPERO__ */
