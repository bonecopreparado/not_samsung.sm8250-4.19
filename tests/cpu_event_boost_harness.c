/* SPDX-License-Identifier: GPL-2.0 */
/* Host-only deterministic workqueue interleavings; no kernel timing claims. */
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks, failures;
static const char *scenario;
#define CHECK(c) do { checks++; if (!(c)) { \
    fprintf(stderr, "FAIL %s: %s (line %d)\n", scenario, #c, __LINE__); \
    failures++; } } while (0)
#define BIT(n) (1UL << (n))
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define to_delayed_work(work) container_of(work, struct delayed_work, work)
#define msecs_to_jiffies(ms) ((unsigned long)(ms))
#define time_after(a, b) ((long)((b) - (a)) < 0)
#ifndef CONFIG_INPUT_BOOST_DURATION_MS
#define CONFIG_INPUT_BOOST_DURATION_MS 300
#endif
#ifndef CONFIG_WAKE_BOOST_DURATION_MS
#define CONFIG_WAKE_BOOST_DURATION_MS 1100
#endif
#define MSM_DRM_EARLY_EVENT_BLANK 1
#define MSM_DRM_BLANK_UNBLANK 0
#define NOTIFY_OK 0
enum { SCREEN_OFF, INPUT_BOOST, MAX_BOOST };
typedef int spinlock_t;
typedef unsigned long atomic_long_t;
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; bool pending; unsigned long due; int bit; };
struct notifier_block { int unused; };
struct msm_drm_notifier { void *data; };
struct boost_drv {
    struct delayed_work input_unboost, max_unboost;
    struct notifier_block msm_drm_notif;
    int boost_waitq;
    spinlock_t boost_lock;
    unsigned long input_boost_expires;
    atomic_long_t max_boost_expires;
    unsigned long state;
};
static int lock_depth;
#define spin_lock_irqsave(lock, flags) do { (void)(lock); (flags) = 0; \
    CHECK(lock_depth == 0); lock_depth++; } while (0)
#define spin_unlock_irqrestore(lock, flags) do { (void)(lock); (void)(flags); \
    CHECK(lock_depth == 1); lock_depth--; } while (0)
static bool test_bit(int bit, const unsigned long *state) { return !!(*state & BIT(bit)); }
static void set_bit(int bit, unsigned long *state) { *state |= BIT(bit); }
static void clear_bit(int bit, unsigned long *state) { *state &= ~BIT(bit); }
static bool test_and_set_bit(int bit, unsigned long *state)
{ bool old = test_bit(bit, state); set_bit(bit, state); return old; }
static bool test_and_clear_bit(int bit, unsigned long *state)
{ bool old = test_bit(bit, state); clear_bit(bit, state); return old; }
static unsigned long atomic_long_read(const atomic_long_t *p) { return *p; }
static unsigned long atomic_long_cmpxchg(atomic_long_t *p, unsigned long old, unsigned long value)
{ unsigned long found = *p; if (found == old) *p = value; return found; }
static unsigned long jiffies;
static int system_unbound_wq;
static unsigned int wakes, queues;
static struct boost_drv *active;
static void input_unboost_worker(struct work_struct *work);
static void max_unboost_worker(struct work_struct *work);
static void __cpu_input_boost_kick(struct boost_drv *b);
static void __cpu_event_boost_kick_max(struct boost_drv *b, unsigned int duration_ms);

enum injection { NONE, OLD_WORKER, NEW_WORKER, EXTEND_BEFORE_REQUEUE };
static enum injection inject;
static void wake_up(int *waitq) { (void)waitq; CHECK(lock_depth == 0); wakes++; }
static void expire(struct delayed_work *work)
{
    work->pending = false;
    if (work->bit == INPUT_BOOST) input_unboost_worker(&work->work);
    else max_unboost_worker(&work->work);
}

static bool mod_delayed_work(int wq, struct delayed_work *work, unsigned long delay)
{
    enum injection current = inject;
    bool was_pending;
    (void)wq;
    CHECK(lock_depth == 0);
    inject = NONE;
    queues++;
    if (current == OLD_WORKER) {
        /* Old callback runs after the new deadline/state is published. */
        expire(work);
    } else if (current == EXTEND_BEFORE_REQUEUE) {
        /* Callback saw a future expiry, but a fresh input extends it before
         * its old remaining-delay request can reach the workqueue. */
        jiffies += 25;
        __cpu_input_boost_kick(active);
    }
    was_pending = work->pending;
    work->pending = true;
    work->due = jiffies + delay;
    if (current == NEW_WORKER) {
        /* The caller is descheduled long enough for its fresh work to expire
         * before mod_delayed_work returns; do not resurrect a completed boost. */
        jiffies = work->due;
        expire(work);
    }
    return was_pending;
}

#include "cpu_event_boost_under_test.h"

static struct boost_drv reset(const char *name)
{
    struct boost_drv b;
    memset(&b, 0, sizeof(b));
    b.input_unboost.bit = INPUT_BOOST;
    b.max_unboost.bit = MAX_BOOST;
    scenario = name;
    jiffies = 1000;
    wakes = queues = 0;
    inject = NONE;
    CHECK(lock_depth == 0);
    return b;
}
static void at_deadline(struct boost_drv *b, int bit)
{
    struct delayed_work *work = bit == INPUT_BOOST ? &b->input_unboost : &b->max_unboost;
    CHECK(work->pending);
    jiffies = work->due;
    expire(work);
}
static void kick(struct boost_drv *b, int bit)
{
    if (bit == INPUT_BOOST) __cpu_input_boost_kick(b);
    else __cpu_event_boost_kick_max(b, 300);
}
static void test_idle_and_pending(int bit)
{
    struct boost_drv b = reset(bit == INPUT_BOOST ? "input idle/extend" : "max idle/extend");
    unsigned int initial_wakes;
    kick(&b, bit);
    CHECK(test_bit(bit, &b.state));
    CHECK(queues == 1 && wakes == 1);
    initial_wakes = wakes;
    jiffies += 100;
    kick(&b, bit);
    CHECK(test_bit(bit, &b.state));
    CHECK(wakes == initial_wakes);
    CHECK(queues == 2);
    at_deadline(&b, bit);
    CHECK(!test_bit(bit, &b.state));
    CHECK(wakes == initial_wakes + 1);
    CHECK(lock_depth == 0);
}
static void test_expiring_old_worker(int bit)
{
    struct boost_drv b = reset(bit == INPUT_BOOST ? "input old worker race" : "max old worker race");
    struct delayed_work *work = bit == INPUT_BOOST ? &b.input_unboost : &b.max_unboost;
    set_bit(bit, &b.state);
    work->pending = true;
    inject = OLD_WORKER;
    kick(&b, bit);
    CHECK(test_bit(bit, &b.state));
    CHECK(work->pending);
    CHECK(work->due == 1300);
    at_deadline(&b, bit);
    CHECK(!test_bit(bit, &b.state));
    CHECK(lock_depth == 0);
}
static void test_fresh_work_expires_before_return(int bit)
{
    struct boost_drv b = reset(bit == INPUT_BOOST ? "input positive-delay preemption" : "max positive-delay preemption");
    struct delayed_work *work = bit == INPUT_BOOST ? &b.input_unboost : &b.max_unboost;
    inject = NEW_WORKER;
    kick(&b, bit);
    CHECK(!test_bit(bit, &b.state));
    CHECK(!work->pending);
    CHECK(jiffies == 1300);
    CHECK(lock_depth == 0);
}
static void test_stale_callback_requeue(void)
{
    struct boost_drv b = reset("input extension races callback requeue");
    active = &b;
    __cpu_input_boost_kick(&b);
    jiffies = 1100;
    inject = EXTEND_BEFORE_REQUEUE;
    expire(&b.input_unboost);
    CHECK(test_bit(INPUT_BOOST, &b.state));
    CHECK(b.input_boost_expires == 1425);
    CHECK(b.input_unboost.due == 1325);
    at_deadline(&b, INPUT_BOOST);
    CHECK(test_bit(INPUT_BOOST, &b.state));
    CHECK(b.input_unboost.pending && b.input_unboost.due == 1425);
    at_deadline(&b, INPUT_BOOST);
    CHECK(!test_bit(INPUT_BOOST, &b.state));
}
static void test_screen_off(void)
{
    struct boost_drv b = reset("screen off");
    set_bit(SCREEN_OFF, &b.state);
    __cpu_input_boost_kick(&b);
    __cpu_event_boost_kick_max(&b, 500);
    CHECK(b.state == BIT(SCREEN_OFF));
    CHECK(!wakes && !queues);
    CHECK(!b.input_boost_expires && !b.max_boost_expires);
}
static void test_max_zero_and_longer(void)
{
    struct boost_drv b = reset("zero max duration is disabled");
    inject = NEW_WORKER;
    __cpu_event_boost_kick_max(&b, 0);
    CHECK(!b.state && !wakes && !queues);
    CHECK(!b.max_boost_expires);
    b = reset("longer max boost preserved");
    __cpu_event_boost_kick_max(&b, 1000);
    jiffies += 10;
    __cpu_event_boost_kick_max(&b, 100);
    CHECK(b.max_boost_expires == 2000);
    CHECK(b.max_unboost.due == 2000);
    CHECK(queues == 1 && wakes == 1);
    CHECK(test_bit(MAX_BOOST, &b.state));
    at_deadline(&b, MAX_BOOST);
    CHECK(!test_bit(MAX_BOOST, &b.state));
}
static void test_input_zero(void)
{
    struct boost_drv b = reset("zero input duration is disabled");
    inject = NEW_WORKER;
    __cpu_input_boost_kick(&b);
    CHECK(!b.state && !wakes && !queues);
    CHECK(!b.input_boost_expires);
}
static void test_display_transition(void)
{
    struct boost_drv b = reset("display unblank always wakes policy thread");
    int blank = MSM_DRM_BLANK_UNBLANK;
    struct msm_drm_notifier event = { &blank };
    set_bit(SCREEN_OFF, &b.state);
    CHECK(msm_drm_notifier_cb(&b.msm_drm_notif,
          MSM_DRM_EARLY_EVENT_BLANK, &event) == NOTIFY_OK);
    CHECK(!test_bit(SCREEN_OFF, &b.state));
    CHECK(wakes > 0);
    if (!CONFIG_WAKE_BOOST_DURATION_MS)
        CHECK(!queues && !test_bit(MAX_BOOST, &b.state));
    blank = 1;
    wakes = 0;
    msm_drm_notifier_cb(&b.msm_drm_notif, MSM_DRM_EARLY_EVENT_BLANK, &event);
    CHECK(test_bit(SCREEN_OFF, &b.state) && wakes == 1);
}
static void test_jiffies_wrap(void)
{
    struct boost_drv b = reset("input deadline across jiffies wrap");
    jiffies = ULONG_MAX - 100;
    __cpu_input_boost_kick(&b);
    CHECK(test_bit(INPUT_BOOST, &b.state));
    CHECK(b.input_boost_expires == 199);
    jiffies = ULONG_MAX - 50;
    expire(&b.input_unboost);
    CHECK(test_bit(INPUT_BOOST, &b.state));
    CHECK(b.input_unboost.pending && b.input_unboost.due == 199);
    at_deadline(&b, INPUT_BOOST);
    CHECK(!test_bit(INPUT_BOOST, &b.state));
}
static void test_max_initial_and_wrap(void)
{
    struct boost_drv b = reset("first max boost before jiffies wrap");
    /* Linux starts jiffies before zero to expose wrap bugs early. */
    jiffies = ULONG_MAX - 1000;
    __cpu_event_boost_kick_max(&b, 300);
    CHECK(test_bit(MAX_BOOST, &b.state));
    CHECK(b.max_boost_expires == ULONG_MAX - 700);
    CHECK(b.max_unboost.pending && queues == 1 && wakes == 1);
    at_deadline(&b, MAX_BOOST);
    CHECK(!test_bit(MAX_BOOST, &b.state));

    b = reset("active max deadline across jiffies wrap");
    jiffies = ULONG_MAX - 100;
    __cpu_event_boost_kick_max(&b, 300);
    CHECK(test_bit(MAX_BOOST, &b.state));
    CHECK(b.max_boost_expires == 199);
    jiffies = ULONG_MAX - 50;
    __cpu_event_boost_kick_max(&b, 100);
    CHECK(b.max_boost_expires == 199 && queues == 1);
    expire(&b.max_unboost);
    CHECK(test_bit(MAX_BOOST, &b.state));
    CHECK(b.max_unboost.pending && b.max_unboost.due == 199);
    at_deadline(&b, MAX_BOOST);
    CHECK(!test_bit(MAX_BOOST, &b.state));
}
int main(void)
{
    if (!CONFIG_INPUT_BOOST_DURATION_MS) {
        test_input_zero();
        test_display_transition();
        printf("%u zero-duration host checks, %u failures\n", checks, failures);
        return failures ? 1 : 0;
    }
    test_idle_and_pending(INPUT_BOOST);
    test_idle_and_pending(MAX_BOOST);
    test_expiring_old_worker(INPUT_BOOST);
    test_expiring_old_worker(MAX_BOOST);
    test_fresh_work_expires_before_return(INPUT_BOOST);
    test_fresh_work_expires_before_return(MAX_BOOST);
    test_stale_callback_requeue();
    test_screen_off();
    test_max_zero_and_longer();
    test_jiffies_wrap();
    test_max_initial_and_wrap();
    test_display_transition();
    printf("%u host checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
