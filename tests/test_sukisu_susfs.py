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
