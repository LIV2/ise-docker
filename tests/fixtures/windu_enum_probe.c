#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int count, found;
static char *math_library;

static void visit(const char *name)
{
    ++count;
    if (strstr(name, "libm.so.6")) {
        ++found;
        if (!math_library)
            math_library = strdup(name);
    }
}

int main(void)
{
    void *library = dlopen("libm.so.6", RTLD_NOW);
    void (*enumerate)(const char *, void (*)(const char *)) =
        dlsym(RTLD_DEFAULT, "wuEnumDLLs");
    if (!library || !enumerate)
        return 10;
    enumerate("", visit);
    if (count < 2 || found != 1)
        return 11;
    count = found = 0;
    enumerate(math_library, visit);
    if (count < 2 || found)
        return 12;
    free(math_library);
    dlclose(library);
    puts("PASS real library enumeration and exclusion");
    return 0;
}
