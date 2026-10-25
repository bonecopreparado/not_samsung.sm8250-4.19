/* SPDX-License-Identifier: GPL-2.0-only */
/* Host shims for the actual allocator and synchronization functions. */
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned int gfp_t;
struct work_struct { void (*func)(struct work_struct *); bool pending; };
struct delayed_work { struct work_struct work; };
struct timer_list { void (*func)(struct timer_list *); };
struct backing_dev_info { int capabilities; const char *name; struct timer_list laptop_mode_wb_timer; };
struct blk_mq_hw_ctx { struct delayed_work run_work; };
struct request_queue {
    int queue_head, id, bio_split, node, icq_list, kobj, sysfs_lock;
    int __queue_lock, *queue_lock, mq_freeze_wq, q_usage_counter;
    void *last_merge, *stats, *mq_ops;
    struct backing_dev_info *backing_dev_info;
    struct timer_list timeout;
    struct work_struct timeout_work;
    struct blk_mq_hw_ctx hctx[2];
    unsigned int nr_hw_queues;
};
#define __GFP_ZERO 1
#define BIO_POOL_SIZE 2
#define BIOSET_NEED_BVECS 1
#define BDI_CAP_CGROUP_WRITEBACK 1
#define PERCPU_REF_INIT_ATOMIC 1
#define GFP_KERNEL 1
#define INIT_LIST_HEAD(p) (*(p) = 0)
#define mutex_init(p) (*(p) = 0)
#define spin_lock_init(p) (*(p) = 0)
#define init_waitqueue_head(p) (*(p) = 0)
#define INIT_WORK(w, fn) do { (w)->func = (fn); (w)->pending = false; } while (0)
#define timer_setup(timer, fn, flags) ((timer)->func = (fn))
#define queue_is_mq(q) (!!(q)->mq_ops)
#define queue_for_each_hw_ctx(q, ctx, index) \
    for ((index) = 0; (unsigned int)(index) < (q)->nr_hw_queues && \
         (((ctx) = &(q)->hctx[index]), 1); (index)++)
#define from_timer(var, timer, member) \
    ((struct request_queue *)((char *)(timer) - offsetof(struct request_queue, member)))

static int blk_requestq_cachep, blk_queue_ida, blk_queue_ktype;
static unsigned int checks, failures, flush_warnings, scheduled, timeout_runs;
static char events[32];
static unsigned int event_count;
#define CHECK(c) do { checks++; if (!(c)) { failures++; \
    fprintf(stderr, "FAIL %s (line %d)\n", #c, __LINE__); } } while (0)
static void *kmem_cache_alloc_node(int cache, gfp_t flags, int node)
{ return calloc(1, sizeof(struct request_queue)); }
static void kmem_cache_free(int cache, void *p) { free(p); }
static int ida_simple_get(int *ida, int start, int end, gfp_t flags) { return 42; }
static void ida_simple_remove(int *ida, int id) { }
static int bioset_init(int *set, int size, int padding, int flags) { return 0; }
static void bioset_exit(int *set) { }
static struct backing_dev_info *bdi_alloc_node(gfp_t flags, int node)
{ return calloc(1, sizeof(struct backing_dev_info)); }
static void bdi_put(struct backing_dev_info *bdi) { free(bdi); }
static void *blk_alloc_queue_stats(void) { return malloc(1); }
static void blk_free_queue_stats(void *stats) { free(stats); }
static void laptop_mode_timer_fn(struct timer_list *timer) { }
static void kobject_init(int *obj, int *type) { }
static void blk_queue_usage_counter_release(int *counter) { }
static int percpu_ref_init(int *ref, void (*release)(int *), int flags, int gfp) { return 0; }
static void percpu_ref_exit(int *ref) { }
static int blkcg_init_queue(struct request_queue *q) { return 0; }
static void blk_queue_reset_io_vol(struct request_queue *q) { }
static void record(char value) { events[event_count++] = value; events[event_count] = '\0'; }
static void del_timer_sync(struct timer_list *timer) { record('T'); }
static void cancel_work_sync(struct work_struct *work)
{
    record('W');
    /* This is the exact __flush_work precondition seen in the device log. */
    if (!work->func)
        flush_warnings++;
    work->pending = false;
}
static void cancel_delayed_work_sync(struct delayed_work *work)
{
    record('D');
    if (!work->work.func)
        flush_warnings++;
    work->work.pending = false;
}
static void kblockd_schedule_work(struct work_struct *work)
{
    scheduled++;
    if (!work->func) {
        flush_warnings++;
        return;
    }
    work->pending = true;
}
static void blk_mq_timeout_work(struct work_struct *work) { timeout_runs++; }

#include "blk_timeout_under_test.h"

static void release_queue(struct request_queue *q)
{
    free(q->stats);
    free(q->backing_dev_info);
    free(q);
}
static void reset_events(void) { event_count = 0; events[0] = '\0'; }

int main(void)
{
    struct request_queue *q = blk_alloc_queue_node(GFP_KERNEL, 0);
    unsigned int warnings_before = flush_warnings;
    CHECK(q != NULL);
    CHECK(q->timeout_work.func != NULL);
    CHECK(q->timeout.func == blk_rq_timed_out_timer);
    reset_events();
    blk_sync_queue(q);
    CHECK(!strcmp(events, "TW"));
    CHECK(flush_warnings == warnings_before);

    /* Bio-based queues can be synchronized without any MQ initialization. */
    q->timeout.func(&q->timeout);
    CHECK(scheduled == 1);
    CHECK(q->timeout_work.pending);
    if (q->timeout_work.func)
        q->timeout_work.func(&q->timeout_work);
    CHECK(timeout_runs == 0);
    reset_events();
    blk_sync_queue(q);
    CHECK(!q->timeout_work.pending);
    CHECK(flush_warnings == warnings_before);

    /* The normal MQ setup still replaces the dummy with the real callback. */
    q->mq_ops = (void *)1;
    init_mq_timeout_under_test(q);
    q->nr_hw_queues = 2;
    INIT_WORK(&q->hctx[0].run_work.work, blk_mq_timeout_work);
    INIT_WORK(&q->hctx[1].run_work.work, blk_mq_timeout_work);
    CHECK(q->timeout_work.func == blk_mq_timeout_work);
    q->timeout_work.pending = true;
    q->hctx[0].run_work.work.pending = q->hctx[1].run_work.work.pending = true;
    reset_events();
    blk_sync_queue(q);
    CHECK(!strcmp(events, "TWDD"));
    CHECK(!q->timeout_work.pending && !q->hctx[0].run_work.work.pending &&
          !q->hctx[1].run_work.work.pending);
    CHECK(flush_warnings == warnings_before);
    release_queue(q);
    printf("%u block timeout checks, %u failures\n", checks, failures);
    return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
