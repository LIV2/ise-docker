#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct vendor_string { void *words[4]; };

static void *symbol(void *library, const char *name)
{
    void *address = dlsym(library, name);
    if (!address) {
        fprintf(stderr, "%s\n", dlerror());
        exit(10);
    }
    return address;
}

int main(void)
{
    void *library = dlopen("libZynqConfig.so", RTLD_NOW | RTLD_GLOBAL);
    if (!library) {
        fprintf(stderr, "%s\n", dlerror());
        return 11;
    }
    void *(*init)(void) = symbol(library, "_ZN11zynq_config4ZTop9test_InitEv");
    int (*change)(void *, const char *, const char *) =
        symbol(RTLD_DEFAULT, "_ZN11zynq_config4ZTop11changeValueEPKcS2_");
    void (*make)(void *, const char *, void *) = symbol(library,
        "_ZN8stlp_std12basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1EPKcRKS4_");
    void (*destroy)(void *) = symbol(library,
        "_ZN8stlp_std12basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEED1Ev");
    void *(*param)(void *, void *) = symbol(library,
        "_ZN11zynq_config4ZTop5paramEN8stlp_std12basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE");
    const char *(*value)(void *) = symbol(library,
        "_ZNK11zynq_config9paramData8getValueEv");
    void (*term)(void) = symbol(library, "_ZN11zynq_config4ZTop9test_TermEv");
    void *top = init();
    if (!top)
        return 12;

    struct vendor_string key = {0};
    char allocator = 0;
    const char *frequency = "pcw::uiparam::ddr::freq_mhz";
    const char *width = "pcw::internal::ddr::dram_width";
    make(&key, frequency, &allocator);
    void *frequency_param = param(top, &key);
    destroy(&key);
    make(&key, width, &allocator);
    void *width_param = param(top, &key);
    destroy(&key);
    char *original_width = strdup(value(&width_param));

    /* Real updates must still reach the native configuration engine. */
    const char *frequencies[] = {"100", "200"};
    for (unsigned int i = 0; i < 2; ++i) {
        if (change(top, frequency, frequencies[i]) != 1)
            return 13;
        if (strcmp(value(&frequency_param), frequencies[i]))
            return 14;
    }
    if (change(top, width, "1") != 0)
        return 15;
    if (strcmp(value(&width_param), original_width))
        return 16;
    if (change(top, width, "") != 0)
        return 17;
    if (strcmp(value(&width_param), original_width))
        return 18;
    if (change(top, "pcw::nonexistent", "x") != 0)
        return 19;
    if (strcmp(value(&frequency_param), "200"))
        return 20;
    free(original_width);
    term();
    puts("PASS valid DDR updates and invalid-input rejection");
    return 0;
}
