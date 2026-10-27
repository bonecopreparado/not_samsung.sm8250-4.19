"""Check real patch application and small extracted pieces of the root integration."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN = "fbc67d004b3b68723e91dd86d50dead1120b4a9a"


def compile_and_run(directory, code, include_dirs=()):
    source = directory / "check.c"
    binary = directory / "check"
    source.write_text(code)
    subprocess.run(["gcc", "-std=gnu11", "-O1", "-g", "-fno-pie", "-no-pie",
                    "-fsanitize=address,undefined",
                    *["-I" + str(path) for path in include_dirs],
                    str(source), "-o", str(binary)],
                   check=True)
    subprocess.run([str(binary)], check=True)


@unittest.skipUnless((ROOT / "KernelSU/kernel/ksu_main.c").exists(),
                     "initialize SukiSU to run its regression tests")
class SukiSUTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sukisu-check-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout",
                        str(ROOT / "KernelSU"), str(self.root / "KernelSU")], check=True)
        subprocess.run(["git", "-C", str(self.root / "KernelSU"), "checkout", "-q", PIN],
                       check=True)
        (self.root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/prepare-sukisu.sh", self.root / "scripts")
        shutil.copytree(ROOT / "patches/sukisu", self.root / "patches/sukisu")

    def prepare(self, check=True):
        return subprocess.run(["bash", "scripts/prepare-sukisu.sh"], cwd=self.root,
                              capture_output=True, text=True, check=check)

    def test_patch_idempotence_and_conflict(self):
        self.prepare()
        source = self.root / "KernelSU/kernel/Makefile"
        patched = source.read_bytes()
        self.prepare()
        self.assertEqual(source.read_bytes(), patched)
        source.write_bytes(patched.replace(b"KSU_VERSION := 41095", b"KSU_VERSION := 49999"))
        modified = source.read_bytes()
        self.assertNotEqual(self.prepare(check=False).returncode, 0)
        self.assertEqual(source.read_bytes(), modified)

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_revoked_root_does_not_escape(self):
        self.prepare()
        source = (self.root / "KernelSU/kernel/feature/sucompat.c").read_text()
        function = source[source.index("int ksu_handle_execveat_sucompat("):]
        function = function[:function.index("\nint ksu_handle_post_execveat_sucompat(")]
        harness = (ROOT / "tests/sukisu_sucompat_harness.c").read_text()
        compile_and_run(self.root, harness.replace("/* FUNCTION_UNDER_TEST */", function))

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_manager_uapi_and_get_info_ioctl(self):
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include "uapi/supercall.h"
int main(void) {
    assert(KERNEL_SU_UAPI_VERSION == 6);
    assert(sizeof(struct ksu_get_info_cmd) == 16);
    assert(KSU_IOCTL_GET_INFO == 0x80104b02U);
    return 0;
}
'''
        compile_and_run(self.root, code,
                        [self.root / "KernelSU/kernel/include"])

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_su_fd_requires_successful_exec(self):
        source = (self.root / "KernelSU/kernel/feature/sucompat.c").read_text()
        function = source[source.index("int ksu_handle_post_execveat_sucompat("):]
        function = function[:function.index("\n#ifdef KSU_COMPAT_USE_STATIC_KEY")]
        code = r'''
#include <assert.h>
#include <stddef.h>
struct filename;
static int installs;
static int ksu_install_su_fd(void) { return ++installs; }
''' + function + r'''
int main(void) {
    int fd = 0, flags = 0, result = -2;
    ksu_handle_post_execveat_sucompat(&fd, NULL, NULL, NULL, &flags, &result);
    assert(installs == 0);
    result = 0;
    ksu_handle_post_execveat_sucompat(&fd, NULL, NULL, NULL, &flags, &result);
    assert(installs == 1);
    return 0;
}
'''
        compile_and_run(self.root, code)

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_legacy_user_paths_and_policy(self):
        self.prepare()
        source = (self.root / "KernelSU/kernel/feature/sucompat.c").read_text()
        functions = source[source.index("static int ksu_handle_path_user("):]
        functions = functions[:functions.index("\n#else\n__attribute__")]
        harness = (ROOT / "tests/sukisu_userpath_harness.c").read_text()
        compile_and_run(self.root, harness.replace("/* FUNCTIONS_UNDER_TEST */", functions))

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_legacy_cpu_spoof_is_unavailable_before_user_copy(self):
        self.prepare()
        source = self.root / "KernelSU/kernel/extension/cpu_spoof.c"
        code = r'''
#include <assert.h>
#include <stddef.h>
#define KSU_NO_CPU_SPOOF
#define __user
typedef unsigned int u32;
''' + '#include "' + str(source) + '"\n' + r'''
int main(void) {
    assert(ksu_extension_cpu_spoof_io(0, NULL) == -EOPNOTSUPP);
    assert(ksu_extension_cpu_spoof_io(0, (void *)1) == -EOPNOTSUPP);
    assert(ksu_extension_cpu_spoof_io(0, (void *)-1) == -EOPNOTSUPP);
    return 0;
}
'''
        compile_and_run(self.root, code)

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_feature_names_match_kernel_specific_uapi(self):
        self.prepare()
        source = (self.root / "KernelSU/kernel/policy/feature.c").read_text()
        table = source[source.index("static const char *const feature_names["):]
        table = table[:table.index("\n};") + len("\n};")]
        for version in ((4, 19, 0), (5, 10, 0)):
            with self.subTest(version=version):
                code = r'''
#include <assert.h>
#include <stddef.h>
#include <string.h>
#define KERNEL_VERSION(a, b, c) (((a) << 16) | ((b) << 8) | (c))
''' + '#define LINUX_VERSION_CODE KERNEL_VERSION(%d, %d, %d)\n' % version + r'''
#include "uapi/feature.h"
''' + table + r'''
int main(void) {
    assert(!strcmp(feature_names[KSU_FEATURE_SU_COMPAT], "su_compat"));
#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)
    assert(!strcmp(feature_names[KSU_FEATURE_SELINUX_HIDE], "selinux_hide"));
#else
    assert(feature_names[4] == NULL);
#endif
    return 0;
}
'''
                compile_and_run(self.root, code,
                                [self.root / "KernelSU/kernel/include"])

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_legacy_devpts_policy_and_susfs_credentials(self):
        self.prepare()
        source = (self.root / "KernelSU/kernel/feature/sucompat.c").read_text()
        devpts = source[source.index("int ksu_handle_devpts("):]
        devpts = devpts[:devpts.index("\n/* 4.19's access/stat")]
        source = (self.root / "KernelSU/kernel/hook/lsm_hook.c").read_text()
        work = source[source.index("static void ksu_handle_extra_susfs_work("):]
        work = work[:work.index("\nstatic int handle_zygote_setresuid(")]
        harness = (ROOT / "tests/sukisu_legacy_hooks_harness.c").read_text()
        code = harness.replace("/* DEVPTS_UNDER_TEST */", devpts)
        code = code.replace("/* WORK_UNDER_TEST */", work)
        compile_and_run(self.root, code)

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_legacy_policy_initializes_susfs_sids_after_unlock(self):
        self.prepare()
        source = (self.root / "KernelSU/kernel/selinux/rules.c").read_text()
        function = source[source.index("void apply_kernelsu_rules(void)"):]
        function = function[:function.index("\n#define KSU_SEPOLICY_MAX_BATCH_SIZE")]
        harness = (ROOT / "tests/sukisu_policy_sid_harness.c").read_text()
        for susfs_enabled in (True, False):
            with self.subTest(susfs_enabled=susfs_enabled):
                config = "#define CONFIG_KSU_SUSFS\n" if susfs_enabled else ""
                code = config + harness.replace("/* FUNCTION_UNDER_TEST */", function)
                compile_and_run(self.root, code)

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_boot_log_rc_is_optional_bounded_and_stops(self):
        self.prepare()
        source = (self.root / "KernelSU/kernel/runtime/ksud.c").read_text()
        rc = source[source.index("static const char KERNEL_SU_RC[]"):
                    source.index("static void stop_vfs_read_hook")]
        harness = r'''
#include <assert.h>
#include <string.h>
#define KERNEL_SU_DOMAIN "ksu"
#define KSUD_PATH "/data/adb/ksud"
/* RC_UNDER_TEST */
int main(void) {
    const char *post = strstr(KERNEL_SU_RC, "on post-fs-data\n");
    const char *modules = strstr(KERNEL_SU_RC, "exec u:r:ksu:s0 root -- /data/adb/ksud post-fs-data");
    const char *boot = strstr(KERNEL_SU_RC, "on property:sys.boot_completed=1\n");
    assert(post && modules && boot);
#ifdef CONFIG_KSU_BOOT_LOG
    const char *start = strstr(post, "    start notkernel_bootlog\n");
    const char *stop = strstr(boot, "    stop notkernel_bootlog\n");
    const char *complete = strstr(boot, "exec u:r:ksu:s0 root -- /data/adb/ksud boot-completed");
    const char *service = strstr(KERNEL_SU_RC, "\nservice notkernel_bootlog /system/bin/logcat ");
    const char *mkdir = strstr(post, "mkdir /data/adb/notkernel-boot 0700 root root\n");
    const char *clear_previous = strstr(post, "rm /data/adb/notkernel-boot/android.previous.log.1\n");
    assert(start && start < modules);
    assert(stop && complete && stop < complete);
    assert(service && strstr(service, "-b main -b system -b crash"));
    assert(strstr(service, "-f /data/adb/notkernel-boot/android.log -r 2048 -n 1 *:W\n"));
    assert(strstr(service, "    seclabel u:r:ksu:s0\n    disabled\n"));
    assert(!strstr(service, "oneshot")); /* retry a slow logd startup */
    assert(mkdir && mkdir < start);
    assert(clear_previous && clear_previous < start);
#else
    assert(!strstr(KERNEL_SU_RC, "notkernel_bootlog"));
    assert(!strstr(KERNEL_SU_RC, "/data/adb/notkernel-boot"));
#endif
    return 0;
}
'''
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                config = "#define CONFIG_KSU_BOOT_LOG\n" if enabled else ""
                compile_and_run(self.root, config + harness.replace("/* RC_UNDER_TEST */", rc))


class SusfsMacroTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_inode_predicate_negation_and_nulls(self):
        header = (ROOT / "include/linux/susfs_def.h").read_text()
        macros = header[header.index("#define SUSFS_IS_INODE_SUS_MAP("):].split("#endif", 1)[0]
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define unlikely(x) (x)
#define AS_FLAGS_SUS_MAP 39
#define AS_FLAGS_OPEN_REDIRECT 36
struct mapping { unsigned long flags; };
struct inode { struct mapping *i_mapping; };
static bool app;
static bool susfs_is_current_proc_umounted_app(void) { return app; }
static bool test_bit(int bit, unsigned long *flags) { return (*flags >> bit) & 1; }
''' + macros + r'''
int main(void) {
    struct mapping map = {0};
    struct inode node = {0}, *p = NULL;
    assert(!SUSFS_IS_INODE_SUS_MAP(p));
    assert(!SUSFS_IS_INODE_OPEN_REDIRECT(p));
    assert(!SUSFS_IS_INODE_OPEN_REDIRECT_WITHOUT_UID_CHECK(p));
    p = &node;
    assert(!SUSFS_IS_INODE_SUS_MAP(p));
    node.i_mapping = &map;
    app = true;
    assert(!SUSFS_IS_INODE_SUS_MAP(p));
    map.flags = (1UL << AS_FLAGS_SUS_MAP) | (1UL << AS_FLAGS_OPEN_REDIRECT);
    assert(SUSFS_IS_INODE_SUS_MAP(p));
    assert(SUSFS_IS_INODE_OPEN_REDIRECT(p));
    assert(SUSFS_IS_INODE_OPEN_REDIRECT_WITHOUT_UID_CHECK(p));
    app = false;
    assert(!SUSFS_IS_INODE_SUS_MAP(p));
    assert(!SUSFS_IS_INODE_OPEN_REDIRECT(p));
    assert(SUSFS_IS_INODE_OPEN_REDIRECT_WITHOUT_UID_CHECK(p));
    assert(true && !SUSFS_IS_INODE_SUS_MAP(p));
    assert(false || !SUSFS_IS_INODE_SUS_MAP(p));
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="susfs-check-") as directory:
            compile_and_run(Path(directory), code)


if __name__ == "__main__":
    unittest.main()
