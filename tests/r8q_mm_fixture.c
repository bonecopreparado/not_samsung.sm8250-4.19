/* SPDX-License-Identifier: GPL-2.0 */
/* Host-only fixture. Actual source functions are inserted by test_r8q_mm.py. */
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;
static int checks;
static const char *scenario;

#define CHECK(condition) do { \
	checks++; \
	if (!(condition)) { \
		printf("FAIL %s: %s (fixture line %d)\n", scenario, #condition, __LINE__); \
		failures++; \
	} \
} while (0)
#define BIT(bit) (1UL << (bit))
#define READ_ONCE(value) (value)
#define BUILD_BUG_ON(condition) ((void)sizeof(char[1 - 2 * !!(condition)]))
#define VM_BUG_ON(condition) CHECK(!(condition))
#define BITS_PER_LONG (sizeof(unsigned long) * CHAR_BIT)
#define BITS_PER_XA_VALUE (BITS_PER_LONG - 1)
#define NODES_SHIFT 2
#define MEM_CGROUP_ID_SHIFT 2
#define EVICTION_SHIFT ((BITS_PER_LONG - BITS_PER_XA_VALUE) + 1 + NODES_SHIFT + MEM_CGROUP_ID_SHIFT)
#define EVICTION_MASK (~0UL >> EVICTION_SHIFT)
#define LRU_GEN_WIDTH 3
#define LRU_REFS_WIDTH 2
#define LRU_REFS_PGOFF 8
#define LRU_REFS_MASK ((BIT(LRU_REFS_WIDTH) - 1) << LRU_REFS_PGOFF)
#define PG_workingset 0
#define LRU_GEN_ANON 0
#define LRU_GEN_FILE 1
#define MAX_NR_GENS 4
#define MAX_NR_TIERS 4
#define FIRST_USER_ADDRESS 4096UL

/* These are aggregate, adjacent counters in this kernel's mmzone.h. */
enum { WORKINGSET_REFAULT, WORKINGSET_ACTIVATE, WORKINGSET_RESTORE };

struct mem_cgroup { int id; };
struct pglist_data { int node_id; int lru_lock; };
typedef struct pglist_data pg_data_t;
struct lru_gen_struct {
	unsigned long min_seq[2];
	unsigned long max_seq;
	long evicted[MAX_NR_GENS][2][MAX_NR_TIERS];
	long refaulted[MAX_NR_GENS][2][MAX_NR_TIERS];
};
struct lruvec { struct lru_gen_struct lrugen; long counters[3]; };
struct page {
	unsigned long flags;
	int file;
	int nr_pages;
	struct mem_cgroup *memcg;
	struct pglist_data *pgdat;
};
struct mm_struct { int mmap_lock; unsigned long highest_vm_end; bool oom; };
struct lru_gen_mm_walk { unsigned long max_seq, next_addr; int batched; };
typedef struct { int unused; } p4d_t;
struct mm_walk { int unused; };
struct mm_walk_ops {
	int (*test_walk)(unsigned long, unsigned long, struct mm_walk *);
	int (*p4d_entry)(p4d_t *, unsigned long, unsigned long, struct mm_walk *);
};

static struct mem_cgroup test_memcg = { 1 };
static struct pglist_data nodes[4];
static struct lruvec test_lruvec;
static unsigned int bucket_order;
static int rcu_depth, mmap_depth, spin_depth;
static bool in_fault, memcg_available, pages_lock_ok, mmap_lock_ok;
static int walk_calls, resched_calls, batch_calls;
static int walk_results[3];
static unsigned long walk_next[3];

#define NODE_DATA(nid) (&nodes[(nid)])
#define page_is_file_cache(page) ((page)->file)
#define hpage_nr_pages(page) ((page)->nr_pages)
#define PageWorkingset(page) (!!((page)->flags & BIT(PG_workingset)))
#define SetPageWorkingset(page) ((page)->flags |= BIT(PG_workingset))
#define page_memcg(page) ((page)->memcg)
#define page_pgdat(page) ((page)->pgdat)
#define lru_hist_from_seq(seq) ((seq) % MAX_NR_GENS)
#define lru_gen_in_fault() (in_fault)
#define DEFINE_MAX_SEQ(lruvec) unsigned long max_seq = READ_ONCE((lruvec)->lrugen.max_seq)

static void *xa_mk_value(unsigned long value) { return (void *)(uintptr_t)((value << 1) | 1); }
static unsigned long xa_to_value(void *entry) { return (unsigned long)((uintptr_t)entry >> 1); }
static bool mem_cgroup_disabled(void) { return false; }
static int mem_cgroup_id(struct mem_cgroup *memcg) { return memcg ? memcg->id : 0; }
static struct mem_cgroup *mem_cgroup_from_id(int id)
{
	return memcg_available && id == test_memcg.id ? &test_memcg : NULL;
}
static struct lruvec *mem_cgroup_lruvec(struct pglist_data *pgdat, struct mem_cgroup *memcg)
{
	(void)pgdat; (void)memcg; return &test_lruvec;
}
static struct mem_cgroup *lruvec_memcg(struct lruvec *lruvec) { (void)lruvec; return &test_memcg; }
static struct pglist_data *lruvec_pgdat(struct lruvec *lruvec) { (void)lruvec; return &nodes[0]; }
static void atomic_long_add(int delta, long *value) { *value += delta; }
static int lru_tier_from_refs(int refs)
{
	int order = 0;
	int value = refs + 1;
	while ((1 << order) < value) order++;
	return order;
}
static void mod_lruvec_state(struct lruvec *lruvec, int item, int delta)
{
	CHECK(item >= 0 && item < 3);
	if (item >= 0 && item < 3) lruvec->counters[item] += delta;
}
static void rcu_read_lock(void) { rcu_depth++; }
static void rcu_read_unlock(void) { CHECK(rcu_depth > 0); rcu_depth--; }
static bool mem_cgroup_trylock_pages(struct mem_cgroup *memcg)
{
	(void)memcg;
	rcu_read_lock();
	if (pages_lock_ok) return true;
	rcu_read_unlock();
	return false;
}
static void mem_cgroup_unlock_pages(void) { rcu_read_unlock(); }
static bool down_read_trylock(int *lock)
{
	(void)lock;
	if (!mmap_lock_ok) return false;
	mmap_depth++;
	return true;
}
static void up_read(int *lock) { (void)lock; CHECK(mmap_depth == 1); mmap_depth--; }
static void spin_lock_irq(int *lock) { (void)lock; spin_depth++; }
static void spin_unlock_irq(int *lock) { (void)lock; CHECK(spin_depth == 1); spin_depth--; }
static bool mm_is_oom_victim(struct mm_struct *mm) { return mm->oom; }
static int should_skip_vma(unsigned long start, unsigned long end, struct mm_walk *walk)
{
	(void)start; (void)end; (void)walk; return 0;
}
static int walk_pud_range(p4d_t *p4d, unsigned long start, unsigned long end, struct mm_walk *walk)
{
	(void)p4d; (void)start; (void)end; (void)walk; return 0;
}
static int walk_page_range(struct mm_struct *mm, unsigned long start, unsigned long end,
			   const struct mm_walk_ops *ops, struct lru_gen_mm_walk *walk)
{
	int call = walk_calls++;
	CHECK(call < 3);
	CHECK(rcu_depth == 1);
	CHECK(mmap_depth == 1);
	CHECK(end == mm->highest_vm_end);
	CHECK(start == (call ? walk_next[call - 1] : FIRST_USER_ADDRESS));
	CHECK(ops->test_walk == should_skip_vma);
	CHECK(ops->p4d_entry == walk_pud_range);
	walk->batched = 2;
	walk->next_addr = walk_next[call];
	return walk_results[call];
}
static void reset_batch_size(struct lruvec *lruvec, struct lru_gen_mm_walk *walk)
{
	(void)lruvec;
	CHECK(spin_depth == 1);
	CHECK(walk->batched > 0);
	walk->batched = 0;
	batch_calls++;
}
static void cond_resched(void)
{
	resched_calls++;
	CHECK(rcu_depth == 0);
	CHECK(mmap_depth == 0);
	CHECK(spin_depth == 0);
}

/* EXTRACT_WORKINGSET_FUNCTIONS */

/* EXTRACT_WALK_MM */

static void reset_fixture(const char *name)
{
	scenario = name;
	memset(&test_lruvec, 0, sizeof(test_lruvec));
	memset(nodes, 0, sizeof(nodes));
	nodes[1].node_id = 1;
	test_lruvec.lrugen.min_seq[0] = test_lruvec.lrugen.min_seq[1] = 5;
	test_lruvec.lrugen.max_seq = 8;
	rcu_depth = mmap_depth = spin_depth = 0;
	in_fault = false;
	memcg_available = pages_lock_ok = mmap_lock_ok = true;
	walk_calls = resched_calls = batch_calls = 0;
	memset(walk_results, 0, sizeof(walk_results));
	memset(walk_next, 0, sizeof(walk_next));
}

static struct page new_page(int file)
{
	struct page page;
	memset(&page, 0, sizeof(page));
	page.file = file;
	page.nr_pages = 3;
	page.memcg = &test_memcg;
	page.pgdat = &nodes[0];
	return page;
}

static void test_eviction(int file)
{
	struct page page;
	void *shadow;
	reset_fixture(file ? "file eviction" : "anon eviction");
	page = new_page(file);
	shadow = lru_gen_eviction(&page);
	CHECK(shadow != NULL);
	CHECK(test_lruvec.lrugen.evicted[1][file][0] == 3);
	CHECK(test_lruvec.counters[WORKINGSET_REFAULT] == 0);
	CHECK(test_lruvec.counters[WORKINGSET_ACTIVATE] == 0);
	CHECK(test_lruvec.counters[WORKINGSET_RESTORE] == 0);
	CHECK(rcu_depth == 0);
}

static void test_refault(int file, bool stale, bool fault)
{
	struct page evicted, replacement;
	void *shadow;
	reset_fixture(file ? (stale ? "file stale refault" : "file recent refault") :
			     (stale ? "anon stale refault" : "anon recent refault"));
	evicted = new_page(file);
	replacement = new_page(file);
	shadow = lru_gen_eviction(&evicted);
	memset(test_lruvec.counters, 0, sizeof(test_lruvec.counters));
	if (stale) test_lruvec.lrugen.min_seq[file]++;
	in_fault = fault;
	lru_gen_refault(&replacement, shadow);
	CHECK(test_lruvec.counters[WORKINGSET_REFAULT] == 3);
	CHECK(test_lruvec.counters[WORKINGSET_ACTIVATE] == (stale ? 0 : 3));
	CHECK(test_lruvec.counters[WORKINGSET_RESTORE] == (!stale && fault ? 3 : 0));
	CHECK(test_lruvec.lrugen.refaulted[1][file][0] == (stale ? 0 : 3));
	CHECK(PageWorkingset(&replacement) == (!stale && fault));
	CHECK(rcu_depth == 0);
}

static void test_refault_rejected(bool wrong_node)
{
	struct page evicted, replacement;
	void *shadow;
	reset_fixture(wrong_node ? "wrong node refault" : "deleted memcg refault");
	evicted = new_page(LRU_GEN_FILE);
	replacement = new_page(LRU_GEN_FILE);
	shadow = lru_gen_eviction(&evicted);
	memset(test_lruvec.counters, 0, sizeof(test_lruvec.counters));
	if (wrong_node) replacement.pgdat = &nodes[1];
	else memcg_available = false;
	lru_gen_refault(&replacement, shadow);
	CHECK(test_lruvec.counters[WORKINGSET_REFAULT] == 0);
	CHECK(test_lruvec.counters[WORKINGSET_ACTIVATE] == 0);
	CHECK(test_lruvec.counters[WORKINGSET_RESTORE] == 0);
	CHECK(rcu_depth == 0);
}

enum walk_case { WALK_OK, WALK_RESTART, WALK_NO_MEMCG, WALK_NO_MMAP,
		 WALK_STALE_SEQ, WALK_ZERO_NEXT, WALK_OOM };

static void test_walker(enum walk_case kind, const char *name)
{
	struct mm_struct mm;
	struct lru_gen_mm_walk walk;
	int expected_walks = 1;
	int expected_resched = 1;
	reset_fixture(name);
	memset(&mm, 0, sizeof(mm));
	memset(&walk, 0, sizeof(walk));
	mm.highest_vm_end = 0x100000UL;
	walk.max_seq = test_lruvec.lrugen.max_seq;
	if (kind == WALK_RESTART) {
		walk_results[0] = -EAGAIN;
		walk_next[0] = 0x2000UL;
		expected_walks = expected_resched = 2;
	} else if (kind == WALK_NO_MEMCG) {
		pages_lock_ok = false;
		expected_walks = expected_resched = 0;
	} else if (kind == WALK_NO_MMAP) {
		mmap_lock_ok = false;
		expected_walks = 0;
	} else if (kind == WALK_STALE_SEQ) {
		walk.max_seq--;
		expected_walks = expected_resched = 0;
	} else if (kind == WALK_ZERO_NEXT) {
		walk_results[0] = -EAGAIN;
	} else if (kind == WALK_OOM) {
		walk_results[0] = -EAGAIN;
		walk_next[0] = 0x2000UL;
		mm.oom = true;
	}
	walk_mm(&test_lruvec, &mm, &walk);
	CHECK(walk_calls == expected_walks);
	CHECK(resched_calls == expected_resched);
	CHECK(batch_calls == expected_walks);
	CHECK(rcu_depth == 0);
	CHECK(mmap_depth == 0);
	CHECK(spin_depth == 0);
	CHECK(walk.batched == 0);
}

int main(void)
{
	int file;
	for (file = LRU_GEN_ANON; file <= LRU_GEN_FILE; file++) {
		test_eviction(file);
		test_refault(file, false, false);
		test_refault(file, true, false);
		test_refault(file, false, true);
	}
	test_refault_rejected(false);
	test_refault_rejected(true);
	test_walker(WALK_OK, "walker success");
	test_walker(WALK_RESTART, "walker restart");
	test_walker(WALK_NO_MEMCG, "walker memcg failure");
	test_walker(WALK_NO_MMAP, "walker mmap trylock failure");
	test_walker(WALK_STALE_SEQ, "walker stale sequence");
	test_walker(WALK_ZERO_NEXT, "walker restart at address zero");
	test_walker(WALK_OOM, "walker OOM exit");
	printf("%s %d host checks, %d failures\n", failures ? "FAIL" : "PASS", checks, failures);
	return failures ? 1 : 0;
}
