"""Check real patch application and small extracted pieces of the root integration."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN = "624727d1077f5afea894f066bcb8ca70079cf802"


def compile_and_run(directory, code):
    source = directory / "check.c"
    binary = directory / "check"
    source.write_text(code)
    subprocess.run(["gcc", "-std=gnu11", "-O1", "-g", "-fno-pie", "-no-pie",
                    "-fsanitize=address,undefined", str(source), "-o", str(binary)],
                   check=True)
    subprocess.run([str(binary)], check=True)


@unittest.skipUnless((ROOT / "KernelSU/kernel/ksu.c").exists(),
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
        source.write_bytes(patched.replace(b"KSU_VERSION := 40545", b"KSU_VERSION := 49999"))
        modified = source.read_bytes()
        self.assertNotEqual(self.prepare(check=False).returncode, 0)
        self.assertEqual(source.read_bytes(), modified)

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_revoked_root_does_not_escape(self):
        self.prepare()
        source = (self.root / "KernelSU/kernel/feature/sucompat.c").read_text()
        function = source[source.index("int ksu_handle_execveat_sucompat("):]
        function = function[:function.index("\nint ksu_handle_execveat(")]
        harness = (ROOT / "tests/sukisu_sucompat_harness.c").read_text()
        compile_and_run(self.root, harness.replace("/* FUNCTION_UNDER_TEST */", function))


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
