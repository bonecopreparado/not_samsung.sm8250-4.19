/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual accounting/sleep fragments with deterministic node-state shims. */
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned int checks, failures, events, wakeups, clears;
static bool mglru_enabled, balanced;
#define CHECK(c) do { checks++; if (!(c)) { failures++; \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)
enum { LRU_KSWAPD_NO_PROGRESS };
typedef struct pglist_data { unsigned int kswapd_failures; int pfmemalloc_wait; } pg_data_t;
struct scan_control { unsigned long nr_reclaimed; };
static bool lru_gen_enabled(void) { return mglru_enabled; }
static void count_vm_event(int event) { CHECK(event == LRU_KSWAPD_NO_PROGRESS); events++; }
static bool waitqueue_active(int *waitq) { return *waitq != 0; }
static void wake_up_all(int *waitq) { (void)waitq; wakeups++; }
static bool pgdat_balanced(pg_data_t *pgdat, int order, int classzone_idx)
{ (void)pgdat; (void)order; (void)classzone_idx; return balanced; }
static void clear_pgdat_congested(pg_data_t *pgdat) { (void)pgdat; clears++; }

#include "kswapd_failure_under_test.h"

int main(void)
{
    unsigned int mode, pass;
    for (mode = 0; mode < 2; mode++) {
        pg_data_t node = {0, 0};
        mglru_enabled = mode;
        balanced = false;
        events = wakeups = clears = 0;
        for (pass = 1; pass <= MAX_RECLAIM_RETRIES; pass++) {
            account_failure(&node, 0);
            CHECK(node.kswapd_failures == pass);
            CHECK(events == pass);
            CHECK(prepare_kswapd_sleep(&node, 0, 0) == (pass == MAX_RECLAIM_RETRIES));
        }
        CHECK(clears == 0 && wakeups == 0);
        reset_on_progress(&node, false);
        CHECK(node.kswapd_failures == MAX_RECLAIM_RETRIES);
        account_failure(&node, 8);
        CHECK(node.kswapd_failures == MAX_RECLAIM_RETRIES);
        CHECK(events == MAX_RECLAIM_RETRIES);
        reset_on_progress(&node, true);
        CHECK(node.kswapd_failures == 0);
        CHECK(!prepare_kswapd_sleep(&node, 0, 0));
        node.pfmemalloc_wait = 1;
        CHECK(!prepare_kswapd_sleep(&node, 0, 0));
        CHECK(wakeups == 1);
        balanced = true;
        CHECK(prepare_kswapd_sleep(&node, 0, 0));
        CHECK(clears == 1 && wakeups == 2);
    }
    printf("%u kswapd failure/progress checks, %u failures\n", checks, failures);
    return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
