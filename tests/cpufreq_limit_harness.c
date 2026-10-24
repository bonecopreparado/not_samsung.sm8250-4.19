#include <errno.h>
#include <limits.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32) && defined(__TINYC__)
#define strtoull _strtoui64
#endif

typedef ptrdiff_t ssize_t;
struct kobject { int unused; };
struct kobj_attribute { int unused; };
static struct {
    unsigned int big_min_freq, big_max_freq, ltl_min_freq, ltl_max_freq;
    unsigned int ltl_min_lock, ltl_divider, hmp_boost_type;
} param;

/*
 * Model lib/kstrtox.c's documented API: 0 on success, -EINVAL/-ERANGE
 * on error, and leave *res unchanged on error. Parse base 0 and accept
 * only an optional terminal newline, as the kernel converter does.
 */
static int kstrtouint(const char *s, unsigned int base, unsigned int *res)
{
    char *end;
    unsigned long long value;
    if (!*s || *s == '-' || *s == ' ' || *s == '\t')
        return -EINVAL;
    errno = 0;
    value = strtoull(s, &end, base);
    if (end == s)
        return -EINVAL;
    if (errno == ERANGE || value > UINT_MAX)
        return -ERANGE;
    if (*end == '\n')
        ++end;
    if (*end)
        return -EINVAL;
    *res = (unsigned int)value;
    return 0;
}
/* The production handlers below are generated from the current kernel source. */
#include "cpufreq_limit_under_test.h"

static int checks, failures;
static void check(const char *label, int ok)
{
    ++checks;
    if (!ok) {
        ++failures;
        fprintf(stderr, "FAIL: %s\n", label);
    }
}
typedef ssize_t (*handler)(struct kobject *, struct kobj_attribute *,
                          const char *, size_t);
static void test_frequency(const char *label, handler store, unsigned int *field)
{
    ssize_t ret;
    *field = 123;
    ret = store(NULL, NULL, "1000\n", 5);
    check(label, ret == 5 && *field == 1000);
    ret = store(NULL, NULL, "bogus\n", 6);
    check("frequency malformed input preserves value",
          ret == -EINVAL && *field == 1000);
    ret = store(NULL, NULL, "4294967296\n", 11);
    check("frequency overflow propagates ERANGE",
          ret == -ERANGE && *field == 1000);
}
int main(void)
{
    ssize_t ret;
    test_frequency("big_min_freq valid", store_big_min_freq, &param.big_min_freq);
    test_frequency("big_max_freq valid", store_big_max_freq, &param.big_max_freq);
    test_frequency("ltl_min_freq valid", store_ltl_min_freq, &param.ltl_min_freq);
    test_frequency("ltl_max_freq valid", store_ltl_max_freq, &param.ltl_max_freq);
    test_frequency("ltl_min_lock valid", store_ltl_min_lock, &param.ltl_min_lock);

    param.ltl_divider = 2;
    ret = store_ltl_divider(NULL, NULL, "1\n", 2);
    check("divider 1 valid", ret == 2 && param.ltl_divider == 1);
    ret = store_ltl_divider(NULL, NULL, "11\n", 3);
    check("divider 11 valid", ret == 3 && param.ltl_divider == 11);
    ret = store_ltl_divider(NULL, NULL, "0\n", 2);
    check("divider zero rejected without change",
          ret == -EINVAL && param.ltl_divider == 11);
    ret = store_ltl_divider(NULL, NULL, "12\n", 3);
    check("divider 12 rejected without change",
          ret == -EINVAL && param.ltl_divider == 11);
    ret = store_ltl_divider(NULL, NULL, "bogus\n", 6);
    check("divider malformed rejected without change",
          ret == -EINVAL && param.ltl_divider == 11);
    ret = store_ltl_divider(NULL, NULL, "4294967296\n", 11);
    check("divider overflow propagates ERANGE",
          ret == -ERANGE && param.ltl_divider == 11);

    param.hmp_boost_type = 0;
    ret = store_hmp_boost_type(NULL, NULL, "2\n", 2);
    check("hmp valid", ret == 2 && param.hmp_boost_type == 2);
    ret = store_hmp_boost_type(NULL, NULL, "bogus\n", 6);
    check("hmp malformed input rejected without change",
          ret == -EINVAL && param.hmp_boost_type == 2);
    ret = store_hmp_boost_type(NULL, NULL, "4294967296\n", 11);
    check("hmp overflow rejected without change",
          ret == -ERANGE && param.hmp_boost_type == 2);

    printf("%d/%d checks passed\n", checks - failures, checks);
    return failures ? 1 : 0;
}
