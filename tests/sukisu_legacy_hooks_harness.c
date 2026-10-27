/* Compile and execute the actual legacy integration functions. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define CONFIG_KSU_SUSFS_SUS_PATH
#define READ_ONCE(x) (x)
typedef uint32_t u32;
typedef unsigned int uid_t;
struct inode_security_struct { u32 sid; };
struct inode { struct inode_security_struct *security; };
struct task { void *mm; };
static struct task task;
#define current (&task)
struct kuid { uid_t val; };
static uid_t uid = 10001;
static bool allowed = true;
static int checks;
u32 ksu_file_sid = 42;
static struct kuid current_uid(void) { return (struct kuid){uid}; }
static bool __ksu_is_allow_uid_for_current(uid_t id) { assert(id == uid); checks++; return allowed; }
static struct inode_security_struct *selinux_inode(struct inode *inode) { return inode->security; }
struct cred { int tag; };
static struct cred caller = {1}, privileged = {2};
struct cred *ksu_cred;
static const struct cred *active_cred = &caller;
static int overrides, loops, restores;
static const struct cred *override_creds(const struct cred *replacement)
{
    assert(replacement == &privileged);
    assert(active_cred == &caller);
    const struct cred *saved = active_cred;
    active_cred = replacement;
    overrides++;
    return saved;
}
static void susfs_run_sus_path_loop(void)
{
    assert(active_cred == ksu_cred);
    loops++;
}
static void revert_creds(const struct cred *saved)
{
    assert(active_cred == &privileged && saved == &caller);
    active_cred = saved;
    restores++;
}

/* DEVPTS_UNDER_TEST */
/* WORK_UNDER_TEST */

int main(void)
{
    struct inode_security_struct sec = {11};
    struct inode inode = {&sec};
    task.mm = &task;
    ksu_handle_devpts(&inode);
    assert(sec.sid == 42 && checks == 1);
    sec.sid = 11;
    allowed = false;
    ksu_handle_devpts(&inode);
    assert(sec.sid == 11 && checks == 2);
    allowed = true;
    uid = 1000;
    ksu_handle_devpts(&inode);
    assert(sec.sid == 11 && checks == 2);
    uid = 110001; /* Root-allowed app in a secondary Android user. */
    ksu_handle_devpts(&inode);
    assert(sec.sid == 42 && checks == 3);
    sec.sid = 11;
    ksu_handle_devpts(0);
    assert(sec.sid == 11);
    task.mm = 0;
    ksu_handle_devpts(&inode);
    assert(sec.sid == 11);
    task.mm = &task;
    ksu_file_sid = 0;
    ksu_handle_devpts(&inode);
    assert(sec.sid == 11);
    ksu_file_sid = 42;
    inode.security = 0;
    ksu_handle_devpts(&inode);
    assert(sec.sid == 11);

    ksu_cred = 0;
    ksu_handle_extra_susfs_work();
    assert(!overrides && !loops && !restores && active_cred == &caller);
    ksu_cred = &privileged;
    ksu_handle_extra_susfs_work();
    assert(overrides == 1 && loops == 1 && restores == 1 && active_cred == &caller);
    ksu_handle_extra_susfs_work();
    assert(overrides == 2 && loops == 2 && restores == 2 && active_cred == &caller);
    return 0;
}
