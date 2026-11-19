/*
 * Validate the obsolete inputs in ISE 14.7's Zynq self-test.
 *
 * The vendor test ignores argv and passes "1" and "" to DDR settings
 * computed by presets. Conflicting internal values become an "ERR: ..."
 * string, which DdrRule::run() converts to zero and uses as a divisor.
 * Only the test launcher preloads this adapter; production tools retain
 * the original Zynq library and rules.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ISE's x86-64 STLport 5.1 ABI, not the build compiler's std::string. */
struct vendor_string {
    void *words[4];
};

struct vendor_vector {
    const char **begin;
    const char **end;
    const char **limit;
};

static int (*change_value)(void *, const char *, const char *);
static void (*string_create)(void *, const char *, void *);
static void (*string_destroy)(void *);
static void *(*find_parameter)(void *, void *);
static void (*get_choices)(void *, void *);
static const char *(*get_value)(void *);
static void (*small_free)(void *, size_t);
static void (*large_free)(void *);
static unsigned int applied, rejected;

static void *symbol(const char *name)
{
    void *address = dlsym(RTLD_NEXT, name);

    if (!address) {
        fprintf(stderr, "zynqconfig_test: incompatible vendor ABI: %s\n",
                dlerror());
        exit(125);
    }
    return address;
}

static void initialize(void)
{
    change_value = symbol("_ZN11zynq_config4ZTop11changeValueEPKcS2_");
    string_create = symbol("_ZN8stlp_std12basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1EPKcRKS4_");
    string_destroy = symbol("_ZN8stlp_std12basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEED1Ev");
    find_parameter = symbol("_ZN11zynq_config4ZTop5paramEN8stlp_std12basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE");
    get_value = symbol("_ZNK11zynq_config9paramData8getValueEv");
    get_choices = symbol("_ZNK3pcw7backend9parameter17getEnabledChoicesERN8stlp_std6vectorIPKcNS2_9allocatorIS5_EEEE");
    small_free = symbol("_ZN8stlp_std12__node_alloc13_M_deallocateEPvm");
    large_free = symbol("_ZdlPv");
}

static void free_choices(struct vendor_vector *choices)
{
    if (choices->begin) {
        size_t bytes = (choices->limit - choices->begin) * sizeof(char *);

        /* Match the allocator selection in the vendor vector destructor. */
        if (bytes <= 128)
            small_free(choices->begin, bytes);
        else
            large_free(choices->begin);
    }
}

int checked_change(void *top, const char *name, const char *value)
    __asm__("_ZN11zynq_config4ZTop11changeValueEPKcS2_");

int checked_change(void *top, const char *name, const char *value)
{
    struct vendor_string key = {0};
    struct vendor_vector choices = {0};
    char allocator = 0;
    void *parameter;
    int valid;

    if (!change_value)
        initialize();
    if (!name || !value)
        goto invalid;

    string_create(&key, name, &allocator);
    parameter = find_parameter(top, &key);
    string_destroy(&key);
    if (!parameter)
        goto invalid;

    /* Internal settings are derived from the public configuration inputs.
     * Let the test reapply a current value, but reject conflicting direct
     * writes before the DDR rules try to interpret their error strings.
     * paramData is a view containing a backend parameter pointer.
     */
    if (!strncmp(name, "pcw::internal::", 15)) {
        if (strcmp(get_value(&parameter), value))
            goto invalid;
        ++applied;
        return change_value(top, name, value);
    }

    /* getEnabledChoices returns the public labels accepted by the UI. */
    get_choices(parameter, &choices);
    valid = choices.begin == choices.end;
    for (const char **item = choices.begin; item != choices.end; ++item)
        if (!strcmp(*item, value))
            valid = 1;
    free_choices(&choices);
    if (!valid)
        goto invalid;

    ++applied;
    return change_value(top, name, value);

invalid:
    ++rejected;
    fprintf(stderr, "zynqconfig_test: rejected invalid test input %s='%s'\n",
            name ? name : "(null)", value ? value : "(null)");
    return 0;
}

__attribute__((destructor)) static void report(void)
{
    if (applied || rejected)
        fprintf(stderr, "zynqconfig_test: applied %u updates; rejected %u invalid inputs\n",
                applied, rejected);
}
