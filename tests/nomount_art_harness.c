/* Host-side fault injection for the actual NoMount ART implementation. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
#define likely(x) (x)
#define unlikely(x) (x)
#define min_t(t, a, b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define GFP_KERNEL 0
struct list_head { struct list_head *next, *prev; };
static struct list_head nomount_rules_list = {
    &nomount_rules_list, &nomount_rules_list
};
static void list_add_tail(struct list_head *node, struct list_head *head)
{
    node->prev = head->prev; node->next = head;
    head->prev->next = node; head->prev = node;
}
static void list_del(struct list_head *node)
{
    node->prev->next = node->next; node->next->prev = node->prev;
}
struct nomount_rule {
    unsigned int target_uid;
    u16 v_len;
    struct list_head list_node;
    struct nomount_rule *next_uid;
    char paths[];
};
#define nm_get_vpath(rule) ((rule)->paths)
static void *nomount_art_root;
static bool fail_alloc;
static unsigned int allocated_nodes;
static void *kzalloc(size_t n, int flags)
{
    (void)flags;
    if (fail_alloc) return NULL;
    void *p = calloc(1, n);
    assert(p); allocated_nodes++;
    return p;
}
static void kfree(void *p)
{
    if (p) { assert(allocated_nodes); allocated_nodes--; free(p); }
}

/* Generated verbatim from the pinned, patched kernel/src/nomount.h. */
#include "nomount_art_under_test.h"

static struct nomount_rule *rule(const char *path, unsigned int uid)
{
    struct nomount_rule *r = calloc(1, sizeof(*r) + strlen(path) + 1);
    assert(r); r->v_len = strlen(path); r->target_uid = uid;
    strcpy(r->paths, path);
    return r;
}
static void remove_rule(struct nomount_rule *r)
{
    nm_art_remove_leaf(&nomount_art_root, r);
    list_del(&r->list_node); free(r);
}
static unsigned int list_count(void)
{
    unsigned int count = 0;
    for (struct list_head *n = nomount_rules_list.next;
         n != &nomount_rules_list; n = n->next) count++;
    return count;
}
static void check_empty(void)
{
    assert(!nomount_art_root && !allocated_nodes && !list_count());
}
static void fail_insertion(struct nomount_rule *r, unsigned int count)
{
    unsigned int before = allocated_nodes;
    fail_alloc = true;
    assert(nm_tree_insert(r) == -ENOMEM);
    fail_alloc = false;
    assert(allocated_nodes == before && list_count() == count);
    assert(!nm_tree_search_exact(r->v_len, r->paths, r->target_uid));
}
static void test_splits(void)
{
    struct nomount_rule *a = rule("/abcd/a", 0);
    struct nomount_rule *b = rule("/abcd/b", 0);
    struct nomount_rule *c = rule("/ax/c", 0);
    assert(!nm_tree_insert(a));
    fail_insertion(b, 1); /* Leaf split. */
    assert(nm_tree_search_exact(a->v_len, a->paths, 0) == a);
    assert(!nm_tree_insert(b));
    fail_insertion(c, 2); /* Internal prefix split. */
    assert(nm_tree_search_exact(a->v_len, a->paths, 0) == a);
    assert(nm_tree_search_exact(b->v_len, b->paths, 0) == b);
    assert(!nm_tree_insert(c));
    remove_rule(b); remove_rule(a); remove_rule(c);
    check_empty();
}
static void test_growth_and_all_bytes(void)
{
    struct nomount_rule *rules[256];
    for (unsigned int i = 0; i < 256; i++) {
        char path[] = {'/', 'p', (char)i, '\0'};
        rules[i] = rule(path, 0);
        if (i == 4 || i == 16 || i == 48) fail_insertion(rules[i], i);
        assert(!nm_tree_insert(rules[i]));
        for (unsigned int j = 0; j <= i; j++)
            assert(nm_tree_search_exact(rules[j]->v_len, rules[j]->paths, 0) == rules[j]);
    }
    assert(((struct art_node *)nomount_art_root)->num_children == 256);
    /* Delete in a permutation, exercising sparse nodes and collapse. */
    for (unsigned int i = 0; i < 256; i++) {
        unsigned int j = (i * 73) % 256;
        remove_rule(rules[j]); rules[j] = NULL;
        for (unsigned int k = 0; k < 256; k++)
            if (rules[k]) assert(nm_tree_search_exact(rules[k]->v_len, rules[k]->paths, 0) == rules[k]);
    }
    check_empty();
}
static void test_uids_and_replacement(void)
{
    struct nomount_rule *a = rule("/same", 10);
    struct nomount_rule *b = rule("/same", 20);
    struct nomount_rule *c = rule("/same", 10);
    assert(!nm_tree_insert(a) && !nm_tree_insert(b) && !nm_tree_insert(c));
    remove_rule(a);
    assert(nm_tree_search_exact(5, "/same", 10) == c);
    assert(nm_tree_search_exact(5, "/same", 20) == b);
    remove_rule(b); remove_rule(c); check_empty();
}
static void test_repeated_updates(void)
{
    struct nomount_rule *rules[512] = {0};
    unsigned int state = 0x12345678;
    for (int i = 0; i < 15000; i++) {
        state ^= state << 13; state ^= state >> 17; state ^= state << 5;
        unsigned int index = state % 512;
        if (rules[index]) { remove_rule(rules[index]); rules[index] = NULL; }
        else {
            char path[80];
            snprintf(path, sizeof(path), "/system/group%u/item%u", index % 17, index);
            rules[index] = rule(path, index % 3);
            assert(!nm_tree_insert(rules[index]));
        }
        for (unsigned int j = 0; j < 512; j++)
            if (rules[j]) assert(nm_tree_search_exact(rules[j]->v_len,
                rules[j]->paths, rules[j]->target_uid) == rules[j]);
    }
    nm_art_free_tree(nomount_art_root); nomount_art_root = NULL;
    for (unsigned int i = 0; i < 512; i++)
        if (rules[i]) { list_del(&rules[i]->list_node); free(rules[i]); }
    check_empty();
}
int main(void)
{
    test_splits(); test_growth_and_all_bytes(); test_uids_and_replacement();
    test_repeated_updates(); puts("NoMount ART fault-injection checks passed");
    return 0;
}
