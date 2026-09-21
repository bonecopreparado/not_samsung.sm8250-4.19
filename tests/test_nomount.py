"""Run the real ART code with allocation failures and validate patch application."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN = "d6cb7158b5a98a8168fa7bae191e23cbcfd38974"


@unittest.skipUnless((ROOT / "NoMount/kernel/src/nomount.h").exists(),
                     "initialize NoMount to run its regression tests")
class NoMountTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nomount-check-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout",
                        str(ROOT / "NoMount"), str(self.root / "NoMount")], check=True)
        subprocess.run(["git", "-C", str(self.root / "NoMount"), "checkout", "-q", PIN], check=True)
        (self.root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/prepare-nomount.sh", self.root / "scripts")
        shutil.copytree(ROOT / "patches/nomount", self.root / "patches/nomount")

    def prepare(self, check=True):
        return subprocess.run(["bash", "scripts/prepare-nomount.sh"], cwd=self.root,
                              check=check, capture_output=True, text=True)

    def test_patch_idempotence_and_conflict(self):
        self.prepare()
        header = self.root / "NoMount/kernel/src/nomount.h"
        patched = header.read_bytes()
        self.prepare()
        self.assertEqual(header.read_bytes(), patched)
        header.write_bytes(patched.replace(b"u16 num_children;", b"unsigned int num_children;"))
        modified = header.read_bytes()
        self.assertNotEqual(self.prepare(check=False).returncode, 0)
        self.assertEqual(header.read_bytes(), modified)

    @unittest.skipUnless(shutil.which("gcc"), "GCC is needed for the host harness")
    def test_art_allocation_failures_and_removal(self):
        self.prepare()
        header = (self.root / "NoMount/kernel/src/nomount.h").read_text()
        code = header.split("/**** Adaptive Radix Tree Protocol ****/", 1)[1]
        code = code.split("/* --- UIDs Array RCU Management --- */", 1)[0]
        (self.root / "nomount_art_under_test.h").write_text(code)
        binary = self.root / "art-check"
        subprocess.run(["gcc", "-std=gnu11", "-O1", "-g", "-fno-omit-frame-pointer",
                        "-fno-pie", "-no-pie", "-fsanitize=address,undefined", "-Wall", "-Wextra",
                        "-I", str(self.root), str(ROOT / "tests/nomount_art_harness.c"),
                        "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
