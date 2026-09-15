"""Offline regression checks for the build/packaging scripts, not kernel tests."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "a" * 40
TOOLS = ("clang", "ld.lld", "llvm-as", "llvm-ar", "llvm-nm", "llvm-objcopy",
         "llvm-objdump", "llvm-strip")

FAKE_MAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["MAKE_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
out = pathlib.Path(next(a[2:] for a in args if a.startswith("O=")))
out.mkdir(parents=True, exist_ok=True)
failure = os.environ.get("FAIL_TARGET")
if failure and any(failure in a for a in args):
    sys.exit(42)
configs = [a for a in args if a.startswith("vendor/")]
if configs:
    (out / ".config").write_text("".join(
        (pathlib.Path("arch/arm64/configs") / c).read_text() for c in configs))
boot = out / "arch/arm64/boot"
if "dtbo.img" in args:
    dts = boot / "dts/vendor/qcom"
    dts.mkdir(parents=True, exist_ok=True)
    mode = os.environ.get("DTB_MODE", "normal")
    if mode != "missing":
        (dts / "b.dtb").write_bytes(b"" if mode == "empty" else b"B")
        (dts / "a board.dtb").write_bytes(b"A")
    if os.environ.get("DTBO_MODE") != "missing":
        (boot / "dtbo.img").write_bytes(
            b"" if os.environ.get("DTBO_MODE") == "empty" else b"DTBO")
for target in ("Image", "Image.gz"):
    if target in args:
        boot.mkdir(parents=True, exist_ok=True)
        if os.environ.get("IMAGE_MODE") != "missing":
            (boot / target).write_bytes(
                b"" if os.environ.get("IMAGE_MODE") == "empty" else b"NEW KERNEL")
'''

FAKE_GIT = r'''#!/usr/bin/env python3
import os, pathlib, sys
args = sys.argv[1:]
if args[0] == "submodule":
    with open(os.environ["GIT_LOG"], "a") as log:
        log.write(repr(args) + "\n")
    if "update" in args and "KernelSU" in args and os.environ.get("KSU_UNAVAILABLE"):
        sys.exit(48)
    if "update" in args and os.environ.get("FAIL_SUBMODULE"):
        sys.exit(43)
    if "status" in args:
        print(" " + "c" * 40 + " KernelSU (fixture)")
elif args[0] == "clone":
    if os.environ.get("FAIL_CLONE"):
        sys.exit(44)
    dest = pathlib.Path(args[-1])
    for name in ("anykernel.sh", "tools/ak3-core.sh",
                 "META-INF/com/google/android/update-binary", ".git/config",
                 "README.md", "Image.gz-dtb", "Image", "dtb", "dtbo.img"):
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("template fixture")
    if os.environ.get("BAD_TEMPLATE"):
        (dest / "tools/ak3-core.sh").unlink()
elif args[0] == "-C":
    if "rev-parse" in args:
        print(os.environ.get("AK3_COMMIT", "b" * 40))
    elif "fetch" in args and os.environ.get("FAIL_AK3_FETCH"):
        sys.exit(45)
elif args[0] == "rev-parse":
    print("a" * 40)
elif args[0] == "status":
    if os.environ.get("DIRTY_SOURCE"):
        print(" M build.sh")
else:
    raise SystemExit("Unexpected git call: " + repr(args))
'''


class BuildScriptsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="not-kernel-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "kernel"
        self.root.mkdir()
        for name in ("build.sh", "build-local.sh", "scripts/not-build-common.sh"):
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        self.bin = Path(self.temp.name) / "bin"
        self.bin.mkdir()
        self.write_command(self.bin / "make", FAKE_MAKE)
        self.write_command(self.bin / "git", FAKE_GIT)
        self.tc = self.root / "tc/clang"
        for name in TOOLS:
            self.write_command(self.tc / "bin" / name,
                               '#!/bin/sh\nprintf "fixture clang 1.0\\n"\n')
        configs = {
            "vendor/kona-perf_defconfig": "CONFIG_BASE=y\n",
            "vendor/samsung/kona-sec-common.config": "CONFIG_COMMON=y\n",
            "vendor/samsung/r8q.config": "CONFIG_SEC_R8Q_PROJECT=y\n",
            "vendor/not/localversion.config": 'CONFIG_LOCALVERSION="-not"\n',
            "vendor/not/ksu.config": "CONFIG_KSU=y\n",
            "vendor/not/permissive.config": "CONFIG_SECURITY_SELINUX_PERMISSIVE=y\n",
        }
        for path, text in configs.items():
            dest = self.root / "arch/arm64/configs" / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
        self.env = os.environ.copy()
        for name in ("DEVICE", "BUILD_VARIANT", "TC_DIR", "JOBS", "CLANG_URL",
                     "CLANG_SHA256", "AK3_COMMIT", "PLATFORM_VERSION"):
            self.env.pop(name, None)
        self.env.update(PATH=str(self.bin) + os.pathsep + self.env["PATH"],
                        JOBS="2", MAKE_LOG=str(self.root / "make.jsonl"),
                        GIT_LOG=str(self.root / "git.log"))
        for name in ("Kconfig", "Makefile"):
            path = self.root / "drivers/kernelsu" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# KernelSU fixture\n")
        (self.root / "arch/arm64/configs/vendor/not/no-ksu.config").write_text(
            "# CONFIG_KSU is not set\n")
        self.old_zip = self.root / "not-previous.zip"
        self.old_zip.write_bytes(b"KEEP OLD BUILD")
        (self.root / "AnyKernel3").mkdir()
        (self.root / "AnyKernel3/local-edit").write_text("KEEP LOCAL EDIT")

    @staticmethod
    def write_command(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)

    def run_build(self, variant="stock", script="build-local.sh", extra=None,
                  args=None, input_text=None):
        env = self.env | (extra or {})
        if args is None:
            args = ["r8q", variant] if script == "build-local.sh" else []
        return subprocess.run(["bash", str(self.root / script), *args],
                              cwd=self.temp.name, env=env, input=input_text,
                              text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=20)

    def packages(self):
        return [p for p in self.root.glob("not-*.zip") if p != self.old_zip]

    def assert_preserved(self):
        self.assertEqual(self.old_zip.read_bytes(), b"KEEP OLD BUILD")
        self.assertEqual((self.root / "AnyKernel3/local-edit").read_text(), "KEEP LOCAL EDIT")
        self.assertEqual(list(self.root.glob(".not-build.*")), [])

    def assert_failure(self, result, message=None):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Build complete:", result.stdout)
        self.assertEqual(self.packages(), [])
        if message:
            self.assertIn(message, result.stdout)
        self.assert_preserved()

    def check_success(self, result, image, variant):
        self.assertEqual(result.returncode, 0, result.stdout)
        archive = Path(next(line.removeprefix("Build complete: ")
                            for line in result.stdout.splitlines()
                            if line.startswith("Build complete: ")))
        with zipfile.ZipFile(archive) as zip_file:
            self.assertIsNone(zip_file.testzip())
            self.assertEqual(zip_file.read(image), b"NEW KERNEL")
            self.assertEqual(zip_file.read("dtb"), b"AB")
            self.assertEqual(zip_file.read("dtbo.img"), b"DTBO")
            names = zip_file.namelist()
            self.assertFalse(any(n.startswith(".git") for n in names))
            self.assertNotIn("Image.gz-dtb", names)
            self.assertNotIn("Image" if image == "Image.gz" else "Image.gz", names)
        info = Path(str(archive) + ".build-info.txt").read_text()
        self.assertIn("source_commit=" + SOURCE_SHA, info)
        self.assertIn("variant=" + variant, info)
        self.assertIn("clang_version=fixture clang 1.0", info)
        check = subprocess.run(["sha256sum", "-c", archive.name + ".sha256"],
                               cwd=self.root, text=True, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        calls = [json.loads(line) for line in (self.root / "make.jsonl").read_text().splitlines()]
        self.assertTrue(all("CC=clang" in call and "-j2" in call for call in calls))
        self.assert_preserved()
        return archive

    def test_local_variants_and_preservation(self):
        for variant in ("stock", "ksu", "ksu+permissive"):
            with self.subTest(variant=variant):
                archive = self.check_success(self.run_build(variant), "Image.gz", variant)
                config = Path(str(archive) + ".config").read_text()
                self.assertEqual("CONFIG_KSU=y" in config, variant != "stock")
                self.assertEqual("CONFIG_SECURITY_SELINUX_PERMISSIVE=y" in config,
                                 variant == "ksu+permissive")
        self.assertEqual(len(self.packages()), 3)

    def test_ci_default_and_override(self):
        self.check_success(self.run_build(script="build.sh", extra={"DEVICE": "r8q"}),
                           "Image", "ksu")
        self.check_success(self.run_build(script="build.sh", extra={
            "DEVICE": "r8q", "BUILD_VARIANT": "stock"}), "Image", "stock")

    def test_interactive(self):
        self.check_success(self.run_build(args=[], input_text="R8Q\nKSU\n"),
                           "Image.gz", "ksu")

    def test_invalid_inputs(self):
        for extra, args in (({}, ["unknown", "stock"]), ({}, ["r8q", "bad"]),
                            ({"JOBS": "0"}, None), ({"JOBS": "-1"}, None),
                            ({"AK3_COMMIT": "main"}, None),
                            ({"CLANG_URL": "https://example.invalid/clang"}, None)):
            with self.subTest(extra=extra, args=args):
                self.assert_failure(self.run_build(extra=extra, args=args))
        self.assert_failure(self.run_build(script="build.sh"), "Set DEVICE")
        self.assertFalse((self.root / "make.jsonl").exists())

    def test_failed_make_never_packages_stale_artifacts(self):
        boot = self.root / "out/arch/arm64/boot"
        for target in ("kona-perf_defconfig", "olddefconfig", "dtbo.img", "Image.gz"):
            with self.subTest(target=target):
                boot.mkdir(parents=True, exist_ok=True)
                (boot / "Image.gz").write_bytes(b"STALE KERNEL")
                (boot / "dtbo.img").write_bytes(b"STALE DTBO")
                result = self.run_build(extra={"FAIL_TARGET": target})
                self.assertEqual(result.returncode, 42, result.stdout)
                self.assert_failure(result)

    def test_stock_without_kernelsu_repository(self):
        shutil.rmtree(self.root / "drivers/kernelsu")
        archive = self.check_success(self.run_build(extra={"KSU_UNAVAILABLE": "1"}),
                                     "Image.gz", "stock")
        self.assertIn("# CONFIG_KSU is not set", Path(str(archive) + ".config").read_text())
        self.assertNotIn("KernelSU", (self.root / "git.log").read_text())

    def test_rooted_variants_require_kernelsu_repository(self):
        for variant in ("ksu", "ksu+permissive"):
            with self.subTest(variant=variant):
                self.assert_failure(self.run_build(variant, extra={"KSU_UNAVAILABLE": "1"}),
                                    "Could not fetch dependencies")
        self.assertFalse((self.root / "make.jsonl").exists())

    def test_rooted_variant_rejects_missing_source(self):
        shutil.rmtree(self.root / "drivers/kernelsu")
        self.assert_failure(self.run_build("ksu"), "KernelSU source is missing")

    def test_missing_or_empty_boot_outputs(self):
        for name in ("DTB_MODE", "DTBO_MODE", "IMAGE_MODE"):
            for mode in ("empty", "missing"):
                with self.subTest(name=name, mode=mode):
                    self.assert_failure(self.run_build(extra={name: mode}))

    def test_dependency_failures(self):
        for env in ("FAIL_SUBMODULE", "FAIL_CLONE", "BAD_TEMPLATE"):
            with self.subTest(env=env):
                self.assert_failure(self.run_build(extra={env: "1"}))

    def test_zip_failure(self):
        self.write_command(self.bin / "zip", "#!/bin/sh\nexit 46\n")
        self.assert_failure(self.run_build())

    def test_incomplete_toolchain(self):
        (self.tc / "bin/clang").unlink()
        self.assert_failure(self.run_build(), "Incomplete toolchain")
        self.assertFalse((self.root / "make.jsonl").exists())

    def test_cached_toolchain_pin_mismatch(self):
        self.assert_failure(self.run_build(extra={"CLANG_URL": "https://example.invalid/clang",
                                                "CLANG_SHA256": "0" * 64}),
                            "Cached Clang does not match")

    def test_anykernel_pin_and_dirty_metadata(self):
        archive = self.check_success(self.run_build(extra={"AK3_COMMIT": "d" * 40,
                                                          "DIRTY_SOURCE": "1"}),
                                     "Image.gz", "stock")
        info = Path(str(archive) + ".build-info.txt").read_text()
        self.assertIn("anykernel_commit=" + "d" * 40, info)
        self.assertIn("source_dirty=true", info)

    def test_build_lock(self):
        lock = self.root / "out/.not-build.lock"
        lock.parent.mkdir()
        with lock.open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assert_failure(self.run_build(), "Another kernel build")

    def prepare_archive(self):
        archive = Path(self.temp.name) / "fixture.tar.zst"
        subprocess.run(["tar", "--zstd", "-cf", str(archive), "-C", str(self.tc.parent),
                        "clang"], check=True)
        shutil.rmtree(self.tc)
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_pinned_download_and_cache_reuse(self):
        archive, digest = self.prepare_archive()
        extra = {"CLANG_URL": archive.as_uri(), "CLANG_SHA256": digest}
        built = self.check_success(self.run_build(extra=extra), "Image.gz", "stock")
        self.assertIn("clang_archive_sha256=" + digest,
                      Path(str(built) + ".build-info.txt").read_text())
        archive.unlink()  # The verified cached compiler must work without re-downloading.
        self.check_success(self.run_build(extra=extra), "Image.gz", "stock")

    def test_download_checksum_failure_leaves_no_cache(self):
        archive, _ = self.prepare_archive()
        self.assert_failure(self.run_build(extra={"CLANG_URL": archive.as_uri(),
                                                "CLANG_SHA256": "0" * 64}), "SHA-256 mismatch")
        self.assertFalse(self.tc.exists())

    def test_interrupted_download_leaves_no_cache(self):
        shutil.rmtree(self.tc)
        self.write_command(self.bin / "curl", "#!/bin/sh\nexit 47\n")
        self.assert_failure(self.run_build(extra={"CLANG_URL": "https://example.invalid/clang",
                                                "CLANG_SHA256": "0" * 64}))
        self.assertFalse(self.tc.exists())


if __name__ == "__main__":
    unittest.main()
