/*
 * ISE 14.7's Wind/U 5.0 loader enumerates ELF objects through _DYNAMIC.
 * libkernel50.so exports that symbol as SHN_ABS, so its relocated GOT
 * entry points at the unmapped address 0x1e6548 on current glibc.
 * Preserve the enumeration and exclusion callback contract through the
 * supported loader API. Only the xilhelp launcher preloads this adapter.
 */
#define _GNU_SOURCE
#include <link.h>
#include <string.h>

struct callback {
    const char *excluded;
    void (*visit)(const char *);
};

static int enumerate(struct dl_phdr_info *info, size_t size, void *data)
{
    struct callback *callback = data;

    (void)size;
    if (info->dlpi_name && strcmp(callback->excluded, info->dlpi_name))
        callback->visit(info->dlpi_name);
    return 0;
}

void wuEnumDLLs(const char *excluded, void (*visit)(const char *))
{
    struct callback callback = { excluded, visit };

    dl_iterate_phdr(enumerate, &callback);
}
