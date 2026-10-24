/* Exercise the actual NoMount payload parser with a mutable caller page. */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define PAGE_SIZE 4096
#undef PATH_MAX
#define PATH_MAX 4096
#define FOLL_WRITE 1
#define GFP_KERNEL 0
#define unlikely(x) (x)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, value) ((x) = (value))
#define offset_in_page(addr) ((addr) & (PAGE_SIZE - 1))

/* Wire definitions and function are extracted verbatim from the patched source. */
#include "nomount_payload_protocol_under_test.h"

struct list_head { int unused; };
#define LIST_HEAD(name) struct list_head name = {0}
#define list_empty(head) ((void)(head), true)
#define list_for_each_entry(pos, head, member) \
    for ((void)(head), (pos) = NULL; (pos); (pos) = NULL)
#define list_for_each_entry_safe(pos, tmp, head, member) \
    for ((void)(head), (pos) = (tmp) = NULL; (pos); (pos) = (tmp))
struct nomount_rule {
    u32 flags, target_uid;
    u16 v_len, r_len;
    struct list_head list_node;
    char paths[];
};
#define nm_get_vpath(rule) ((rule)->paths)
#define nm_get_rpath(rule) ((rule)->paths + (rule)->v_len + 1)
struct nm_uid_array { int count; u32 uids[]; };
static struct nm_uid_array *nomount_uids;
static struct list_head nomount_rules_list;
static int nomount_rwsem, nomount_srcu;
#define down_write(p) ((void)(p))
#define up_write(p) ((void)(p))
#define down_read(p) ((void)(p))
#define up_read(p) ((void)(p))
#define rcu_read_lock() ((void)0)
#define rcu_read_unlock() ((void)0)
#define rcu_dereference(p) (p)
#define synchronize_rcu() ((void)0)
#define synchronize_srcu(p) ((void)(p))
static void nm_free_rule(struct nomount_rule *rule) { (void)rule; }
static int nm_uid_add(unsigned int uid) { (void)uid; return 0; }
static int nm_uid_del(unsigned int uid) { (void)uid; return 0; }
static void __nomount_clear_all(int flags) { (void)flags; }

struct page { int unused; };
static struct page caller_page;
static struct nm_payload *request;
static bool fail_pin, fail_alloc, mutate_snapshot, mutate_next_header;
static unsigned int pins, maps, dirty_pages, allocations, adds, deletes;
static size_t next_header;
static unsigned int expected_uid;

static int get_user_pages_fast(unsigned long addr, int nr, int flags, struct page **page)
{
    (void)addr;
    assert(nr == 1 && flags == FOLL_WRITE);
    if (fail_pin) return 0;
    *page = &caller_page;
    pins++;
    return 1;
}
static void *kmap(struct page *page)
{
    assert(page == &caller_page);
    maps++;
    return request;
}
static void kunmap(struct page *page)
{
    assert(page == &caller_page && maps);
    maps--;
}
static void put_page(struct page *page)
{
    assert(page == &caller_page && pins);
    pins--;
}
static void set_page_dirty_lock(struct page *page)
{
    assert(page == &caller_page);
    dirty_pages++;
}
static void *kmemdup(const void *src, size_t size, int flags)
{
    (void)flags;
    if (fail_alloc) return NULL;
    void *copy = malloc(size);
    assert(copy);
    memcpy(copy, src, size);
    allocations++;
    if (mutate_snapshot) {
        /* Simulate a second caller thread changing command fields after copying. */
        request->cmd = NM_CMD_CLEAR_ALL;
        request->arg1 = UINT32_MAX;
        request->data_size = UINT32_MAX;
        memset(request->buffer, 0xff, sizeof(request->buffer));
    }
    return copy;
}
static void kfree(void *ptr)
{
    assert(ptr && allocations);
    allocations--;
    free(ptr);
}
static int __nomount_add_rule(const char *v_path, const char *r_path,
                             u16 v_len, u16 r_len, u32 flags, unsigned int uid,
                             struct list_head *victims)
{
    (void)flags;
    (void)victims;
    assert(v_len == 2 && r_len == 2 && uid == expected_uid);
    assert(!memcmp(v_path, "/v", 2) && !memcmp(r_path, "/r", 2));
    adds++;
    if (mutate_next_header) {
        struct nm_rule_hdr *next = (void *)(request->buffer + next_header);
        next->v_len = next->r_len = UINT16_MAX;
    }
    return 0;
}
static void __nomount_del_rule(const char *v_path, u16 v_len, unsigned int uid,
                              struct list_head *victims)
{
    (void)victims;
    assert(v_len == 2 && uid == expected_uid && !memcmp(v_path, "/v", 2));
    deletes++;
}

#include "nomount_payload_function_under_test.h"

static void reset_request(u32 cmd)
{
    assert(!pins && !maps && !allocations);
    memset(request, 0, sizeof(*request));
    request->magic = NOMOUNT_MAGIC_SIG;
    request->cmd = cmd;
    fail_pin = fail_alloc = mutate_snapshot = mutate_next_header = false;
    dirty_pages = adds = deletes = 0;
    expected_uid = 10001;
}
static void process(void)
{
    assert(nm_process_payload(0) == 0);
    assert(!pins && !maps && !allocations && dirty_pages == 1);
}
static size_t append_rule(size_t offset)
{
    struct nm_rule_hdr header = {.uid = expected_uid, .v_len = 2, .r_len = 2};
    memcpy(request->buffer + offset, &header, sizeof(header));
    memcpy(request->buffer + offset + sizeof(header), "/v/r", 4);
    return offset + sizeof(header) + 4;
}
static void test_rule_bounds(void)
{
    const u32 bad_offsets[] = {1, 4068, 4096, UINT32_MAX};
    for (unsigned int cmd = NM_CMD_ADD_RULE; cmd <= NM_CMD_DEL_RULE; cmd++) {
        for (unsigned int i = 0; i < sizeof(bad_offsets) / sizeof(*bad_offsets); i++) {
            reset_request(cmd);
            request->arg1 = bad_offsets[i];
            process();
            assert(request->status == -EINVAL && !adds && !deletes);
        }
        reset_request(cmd);
        request->data_size = sizeof(request->buffer) + 1;
        process();
        assert(request->status == -EINVAL && !adds && !deletes);

        reset_request(cmd);
        request->arg1 = request->data_size = sizeof(request->buffer);
        process();
        assert(!adds && !deletes);
        assert(request->status == (cmd == NM_CMD_ADD_RULE ? 0 : -ENOENT));
    }
}
static void test_valid_rules_and_snapshot(void)
{
    reset_request(NM_CMD_ADD_RULE);
    next_header = append_rule(0);
    request->data_size = append_rule(next_header);
    mutate_next_header = true;
    process();
    assert(adds == 2 && request->status == 0);
    assert(request->arg1 == request->data_size);

    reset_request(NM_CMD_ADD_RULE);
    request->data_size = append_rule(0);
    mutate_snapshot = true;
    process();
    assert(adds == 1 && request->status == 0 && request->cmd == NM_CMD_ADD_RULE);

    reset_request(NM_CMD_ADD_RULE);
    request->arg1 = append_rule(0);
    request->data_size = append_rule(request->arg1);
    process();
    assert(adds == 1 && request->arg1 == request->data_size);

    reset_request(NM_CMD_DEL_RULE);
    struct nm_del_hdr header = {.uid = expected_uid, .v_len = 2};
    memcpy(request->buffer, &header, sizeof(header));
    memcpy(request->buffer + sizeof(header), "/v", 2);
    request->data_size = sizeof(header) + 2;
    mutate_snapshot = true;
    process();
    assert(deletes == 1 && request->arg1 == request->data_size);
}
static void test_uid_cursors(void)
{
    const u32 cursors[] = {0, 1, 3, 4, INT_MAX, 0x80000000U, UINT32_MAX};
    nomount_uids = malloc(sizeof(*nomount_uids) + 3 * sizeof(u32));
    assert(nomount_uids);
    nomount_uids->count = 3;
    for (unsigned int i = 0; i < 3; i++) nomount_uids->uids[i] = 10001 + i;
    for (unsigned int i = 0; i < sizeof(cursors) / sizeof(*cursors); i++) {
        reset_request(NM_CMD_GET_UIDS);
        request->arg1 = cursors[i];
        process();
        u32 count = cursors[i] < 3 ? 3 - cursors[i] : 0;
        assert(request->data_size == count * sizeof(u32));
        assert(request->arg1 == cursors[i] + count);
        for (unsigned int j = 0; j < count; j++) {
            u32 uid;
            memcpy(&uid, request->buffer + j * sizeof(uid), sizeof(uid));
            assert(uid == 10001 + cursors[i] + j);
        }
    }
    free(nomount_uids);
    nomount_uids = NULL;
}
static void test_failure_cleanup(void)
{
    reset_request(NM_CMD_GET_VERSION);
    fail_alloc = true;
    assert(nm_process_payload(0) == -ENOMEM);
    assert(request->status == -ENOMEM);
    assert(!pins && !maps && !allocations && dirty_pages == 1);
    reset_request(NM_CMD_GET_VERSION);
    request->magic = 0;
    assert(nm_process_payload(0) == -EFAULT);
    assert(!pins && !maps && !allocations && !dirty_pages);
    reset_request(NM_CMD_GET_VERSION);
    fail_pin = true;
    assert(nm_process_payload(0) == -EFAULT);
    assert(!pins && !maps && !allocations && !dirty_pages);
    reset_request(NM_CMD_GET_VERSION);
    assert(nm_process_payload(1) == -EFAULT);
    assert(!pins && !maps && !allocations && !dirty_pages);
    reset_request(NM_CMD_GET_VERSION);
    process();
    assert(request->data_size == strlen(NOMOUNT_VERSION));
    assert(!memcmp(request->buffer, NOMOUNT_VERSION, request->data_size));
}
int main(void)
{
    assert(sizeof(struct nm_payload) == PAGE_SIZE);
    request = malloc(sizeof(*request));
    assert(request);
    test_rule_bounds();
    test_valid_rules_and_snapshot();
    test_uid_cursors();
    test_failure_cleanup();
    free(request);
    return 0;
}
