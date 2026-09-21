/* Narrow host regression: execute the real sucompat handler with mocked policy. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define __user
#define unlikely(x) (x)
#define likely(x) (x)
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define SUSFS_MAX_LEN_PATHNAME 256
#define GFP_KERNEL 0
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
typedef unsigned int uid_t;
struct kuid { uid_t val; };
struct filename { const char *name; };
struct user_arg_ptr { int unused; };
struct ksu_sulog_pending_event { int unused; };
static const char su_path[] = "/system/bin/su";
static const char ksud_path[] = "/data/adb/ksud";
static bool allowed;
static int escaped, checks;
static const char *get_user_arg_ptr(struct user_arg_ptr argv, int nr) { return "su"; }
static struct kuid current_uid(void) { return (struct kuid){10001}; }
static bool __ksu_is_allow_uid_for_current(uid_t uid) { checks++; return allowed; }
static int ksu_handle_execveat_init(struct filename *f, struct user_arg_ptr *a,
                                  struct user_arg_ptr *e) { return -1; }
static int escape_with_root_profile(void) { escaped++; return 0; }
static struct ksu_sulog_pending_event *ksu_sulog_capture_sucompat(
    const char *name, struct user_arg_ptr *a, int gfp) { return NULL; }
static void ksu_sulog_emit_pending(struct ksu_sulog_pending_event *p, int ret, int gfp) {}

/* FUNCTION_UNDER_TEST */

int main(void)
{
    char path[SUSFS_MAX_LEN_PATHNAME];
    struct filename name = {path}, *filename = &name;
    struct user_arg_ptr args = {0};
    int fd = 0, flags = 0;

    strcpy(path, su_path);
    allowed = false;
    ksu_handle_execveat_sucompat(&fd, &filename, &args, &args, &flags);
    assert(checks == 1 && escaped == 0);
    assert(!strcmp(path, su_path));

    allowed = true;
    ksu_handle_execveat_sucompat(&fd, &filename, &args, &args, &flags);
    assert(checks == 2 && escaped == 1);
    assert(!strcmp(path, ksud_path));

    /* Revoke while the same simulated task remains alive. */
    allowed = false;
    strcpy(path, su_path);
    ksu_handle_execveat_sucompat(&fd, &filename, &args, &args, &flags);
    assert(checks == 3 && escaped == 1);
    assert(!strcmp(path, su_path));
    return 0;
}
