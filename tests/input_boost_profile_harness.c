/* SPDX-License-Identifier: GPL-2.0-only */
#include <stdio.h>
#include <stdlib.h>

#ifndef CONFIG_INPUT_BOOST_TO_MAX
#define CONFIG_INPUT_BOOST_TO_MAX 0
#endif
#define IS_ENABLED(option) (option)
#define CONFIG_INPUT_BOOST_FREQ_LP 883200U
#define CONFIG_INPUT_BOOST_FREQ_PERF 825600U
#define CONFIG_INPUT_BOOST_FREQ_PERFP 0U
#define min(a, b) ((a) < (b) ? (a) : (b))
static int lp = 0, perf = 1;
#define cpu_lp_mask (&lp)
#define cpu_perf_mask (&perf)
static int cpumask_test_cpu(unsigned int cpu, const int *mask)
{ return cpu == (unsigned int)*mask; }
struct cpufreq_policy { unsigned int cpu, max; };

#include "input_boost_profile_under_test.h"

int main(void)
{
    const unsigned int ceilings[] = {4000000, 600000, 300000, 0};
    const unsigned int defaults[] = {883200, 825600, 0};
    unsigned int cpu, i, checks = 0;
    for (cpu = 0; cpu < 3; cpu++) {
        for (i = 0; i < sizeof(ceilings) / sizeof(ceilings[0]); i++) {
            struct cpufreq_policy policy = {cpu, ceilings[i]};
            unsigned int expected = CONFIG_INPUT_BOOST_TO_MAX ? policy.max :
                                    min(defaults[cpu], policy.max);
            unsigned int actual = get_input_boost_freq(&policy);
            checks++;
            if (actual != expected) {
                fprintf(stderr, "FAIL cpu=%u ceiling=%u actual=%u expected=%u\n",
                        cpu, policy.max, actual, expected);
                return EXIT_FAILURE;
            }
        }
    }
    printf("%u input profile checks passed (%s)\n", checks,
           CONFIG_INPUT_BOOST_TO_MAX ? "burst" : "balanced");
    return EXIT_SUCCESS;
}
