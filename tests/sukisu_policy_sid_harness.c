/* Exercise the actual legacy apply_kernelsu_rules() control flow. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>

#define KERNEL_VERSION(a, b, c) (((a) << 16) | ((b) << 8) | ((c) > 255 ? 255 : (c)))
#define LINUX_VERSION_CODE KERNEL_VERSION(4, 19, 325)
#define likely(value) (value)
#define pr_info(...) ((void)0)

typedef unsigned long cpumask_t;
typedef int rwlock_t;
struct policydb { int applied; };
struct sched_param { int sched_priority; };
struct task_struct {
    void *mm;
    int policy;
    int rt_priority;
    cpumask_t cpus;
};

static struct policydb policy;
static struct task_struct task, *current = &task;
static rwlock_t policy_lock;
static bool have_lock, lock_held, stop_active;
static int phase, preempt_count, scheduler_calls, stop_calls, sid_calls;
static const cpumask_t original_mask = 0xf, pinned_mask = 1UL << 2;

static bool getenforce(void) { return true; }
static struct policydb *get_policydb(void) { return &policy; }
static rwlock_t *ksu_get_policy_rwlock(void)
{
    return have_lock ? &policy_lock : NULL;
}
static cpumask_t *ksu_get_current_cpumask_t(void) { return &current->cpus; }
static void cpumask_copy(cpumask_t *dst, const cpumask_t *src) { *dst = *src; }
static int raw_smp_processor_id(void) { return 2; }
static const cpumask_t *cpumask_of(int cpu)
{
    assert(cpu == 2);
    return &pinned_mask;
}
static int set_cpus_allowed_ptr(struct task_struct *t, const cpumask_t *mask)
{
    assert(t == current);
    assert(!lock_held && preempt_count == 0);
    t->cpus = *mask;
    return 0;
}
static void write_lock(rwlock_t *lock)
{
    assert(lock == &policy_lock && !lock_held);
    lock_held = true;
    ++preempt_count;
}
static void preempt_enable(void)
{
    assert(preempt_count == 1);
    --preempt_count;
}
static void preempt_disable(void)
{
    assert(preempt_count == 0);
    ++preempt_count;
}
static void write_unlock(rwlock_t *lock)
{
    assert(lock == &policy_lock && lock_held && preempt_count == 1);
    lock_held = false;
    --preempt_count;
}
static int sched_setscheduler_nocheck(struct task_struct *t, int scheduler,
                                    const struct sched_param *param)
{
    assert(t == current && t->mm && lock_held);
    t->policy = scheduler;
    t->rt_priority = param->sched_priority;
    ++scheduler_calls;
    return 0;
}
static int apply_kernelsu_rules_fn(void *db)
{
    assert(db == &policy && phase == 0);
    assert(lock_held == have_lock && stop_active == !have_lock);
    assert(current->cpus == (have_lock ? pinned_mask : original_mask));
    if (have_lock && current->mm) {
        assert(current->policy == 1 && current->rt_priority == 50);
    }
    policy.applied = 1;
    phase = 1;
    return 0;
}
static int stop_machine(int (*fn)(void *), void *arg, const cpumask_t *mask)
{
    int ret;
    assert(!have_lock && !lock_held && !mask);
    ++stop_calls;
    stop_active = true;
    ret = fn(arg);
    stop_active = false;
    return ret;
}
static void smp_mb(void) { assert(phase == 1); }
static void reset_avc_cache(void)
{
    assert(policy.applied && phase == 1);
    assert(!lock_held && !stop_active && preempt_count == 0);
    assert(current->cpus == original_mask);
    assert(current->policy == 0 && current->rt_priority == 0);
    phase = 2;
}
#ifdef CONFIG_KSU_SUSFS
static void susfs_set_batch_sid(void)
{
    /* SID resolution can acquire the policy read lock. It must run only
     * after the write lock/stop_machine section and AVC cache reset. */
    assert(policy.applied && phase == 2);
    assert(!lock_held && !stop_active && preempt_count == 0);
    ++sid_calls;
    phase = 3;
}
#endif

/* FUNCTION_UNDER_TEST */

static void check_path(bool with_lock, bool with_mm)
{
    have_lock = with_lock;
    task.mm = with_mm ? &task : NULL;
    task.policy = task.rt_priority = 0;
    task.cpus = original_mask;
    phase = policy.applied = preempt_count = 0;
    scheduler_calls = stop_calls = sid_calls = 0;
    lock_held = stop_active = false;

    apply_kernelsu_rules();

    assert(policy.applied == 1);
    assert(!lock_held && !stop_active && preempt_count == 0);
    assert(task.cpus == original_mask);
    assert(task.policy == 0 && task.rt_priority == 0);
    assert(scheduler_calls == (with_lock && with_mm ? 2 : 0));
    assert(stop_calls == (with_lock ? 0 : 1));
#ifdef CONFIG_KSU_SUSFS
    assert(sid_calls == 1 && phase == 3);
#else
    assert(sid_calls == 0 && phase == 2);
#endif
}

int main(void)
{
    check_path(true, true);
    check_path(true, false);
    check_path(false, true);
    check_path(false, false);
    return 0;
}
