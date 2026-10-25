/* SPDX-License-Identifier: GPL-2.0-only */
/* Host-only frequency selection; does not exercise hardware throttling. */
#include <stdio.h>
#include <stdlib.h>
#define max(a, b) ((a) > (b) ? (a) : (b))
#include "qcom_cpufreq_definitions_under_test.h"
#include "qcom_cpufreq_selection_under_test.h"

static unsigned int checks, failures;
#define ROW(freq, bits) { .frequency = (freq), .flags = (bits) }
#define END ROW(CPUFREQ_TABLE_END, 0)
#define CHECK(table, expected) do { \
    unsigned int got = qcom_cpufreq_hw_max_non_boost(table); \
    checks++; if (got != (expected)) { failures++; \
    fprintf(stderr, "FAIL %s: got %u, expected %u\n", #table, got, (unsigned int)(expected)); } \
} while (0)

int main(void)
{
    /* Realistic DT filtering can invalidate either end of a hardware LUT. */
    struct cpufreq_frequency_table ascending[] = {
        ROW(614400, 0), ROW(1075200, 0), ROW(1804800, 0), END };
    struct cpufreq_frequency_table trailing_invalid[] = {
        ROW(614400, 0), ROW(1804800, 0), ROW(CPUFREQ_ENTRY_INVALID, 0),
        ROW(CPUFREQ_ENTRY_INVALID, 0), END };
    struct cpufreq_frequency_table filtered_both_ends[] = {
        ROW(CPUFREQ_ENTRY_INVALID, 0), ROW(825600, 0),
        ROW(CPUFREQ_ENTRY_INVALID, 0), ROW(2419200, 0),
        ROW(CPUFREQ_ENTRY_INVALID, 0), END };
    struct cpufreq_frequency_table boost_tail[] = {
        ROW(844800, 0), ROW(2745600, 0), ROW(2841600, CPUFREQ_BOOST_FREQ), END };
    /* cpufreq.h explicitly allows a table that is not ascending. */
    struct cpufreq_frequency_table unsorted[] = {
        ROW(2419200, 0), ROW(825600, 0), ROW(1478400, 0), END };
    struct cpufreq_frequency_table boost_before_normal[] = {
        ROW(844800, 0), ROW(2841600, CPUFREQ_BOOST_FREQ), ROW(2745600, 0), END };
    struct cpufreq_frequency_table boost_with_other_flags[] = {
        ROW(1804800, 2), ROW(2000000, CPUFREQ_BOOST_FREQ | 2), END };
    struct cpufreq_frequency_table only_boost[] = {
        ROW(2841600, CPUFREQ_BOOST_FREQ), END };
    struct cpufreq_frequency_table invalid_boost[] = {
        ROW(1804800, 0), ROW(CPUFREQ_ENTRY_INVALID, CPUFREQ_BOOST_FREQ),
        ROW(614400, 0), END };
    struct cpufreq_frequency_table all_invalid[] = {
        ROW(CPUFREQ_ENTRY_INVALID, 0), ROW(CPUFREQ_ENTRY_INVALID, 0), END };
    struct cpufreq_frequency_table empty[] = { END };
    struct cpufreq_frequency_table single[] = { ROW(1804800, 0), END };
    struct cpufreq_frequency_table sentinel_stops[] = {
        ROW(1804800, 0), END, ROW(4000000, 0), END };

    CHECK(ascending, 1804800);
    CHECK(trailing_invalid, 1804800);
    CHECK(filtered_both_ends, 2419200);
    CHECK(boost_tail, 2745600);
    CHECK(unsorted, 2419200);
    CHECK(boost_before_normal, 2745600);
    CHECK(boost_with_other_flags, 1804800);
    CHECK(only_boost, 0);
    CHECK(invalid_boost, 1804800);
    CHECK(all_invalid, 0);
    CHECK(empty, 0);
    CHECK(single, 1804800);
    CHECK(sentinel_stops, 1804800);
    printf("%u qcom LUT selection checks, %u failures\n", checks, failures);
    return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
