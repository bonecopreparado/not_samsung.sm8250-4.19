/* Execute the actual patched handlers with the legacy nofault copy semantics. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#define __user
#define READ_ONCE(x) (x)
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define pr_info(...) ((void)0)
struct kuid { unsigned val; };
static const char su_path[] = "/system/bin/su";
static char sh_path[] = "/system/bin/sh";
static bool ksu_su_compat_enabled = true;
static bool allowed = true, chrooted, copy_fault, stack_fault;
static int copies;
static struct kuid current_uid(void) { return (struct kuid){10001}; }
static bool __ksu_is_allow_uid_for_current(unsigned uid) { return allowed; }
static bool current_chrooted(void) { return chrooted; }
static char *sh_user_path(void) { return stack_fault ? NULL : sh_path; }
static long ksu_strncpy_from_user_nofault(char *dst, const char *src, long count)
{
    copies++;
    if (copy_fault)
        return -EFAULT;
    size_t len = strlen(src);
    strncpy(dst, src, count);
    if (len >= (size_t)count) {
        dst[count - 1] = '\0';
        return count;
    }
    return len + 1;
}

/* FUNCTIONS_UNDER_TEST */

static void check_both(const char *input, bool rewrite)
{
    int fd = 0, mode = 0, flags = 0;
    const char *path = input;
    ksu_handle_faccessat(&fd, &path, &mode, &flags);
    assert(path == (rewrite ? sh_path : input));
    path = input;
    ksu_handle_stat(&fd, &path, &flags);
    assert(path == (rewrite ? sh_path : input));
}

int main(void)
{
    check_both(su_path, true);
    /* A full-buffer nofault copy must not turn a prefix into an exact match. */
    check_both("/system/bin/sux", false);
    check_both("/system/bin/su/", false);
    check_both("/system/bin/s", false);
    check_both("", false);
    check_both("/other/path", false);
    allowed = false;
    int before = copies;
    check_both(su_path, false);
    assert(copies == before);
    allowed = true;
    ksu_su_compat_enabled = false;
    check_both(su_path, false);
    ksu_su_compat_enabled = true;
    chrooted = true;
    check_both(su_path, false);
    chrooted = false;
    stack_fault = true;
    check_both(su_path, false);
    stack_fault = false;
    copy_fault = true;
    check_both((const char *)1, false);
    copy_fault = false;
    check_both(NULL, false);
    check_both((const char *)(uintptr_t)-EFAULT, false);
    int fd = 0, mode = 0, flags = 0;
    ksu_handle_faccessat(&fd, NULL, &mode, &flags);
    ksu_handle_stat(&fd, NULL, &flags);
    return 0;
}
