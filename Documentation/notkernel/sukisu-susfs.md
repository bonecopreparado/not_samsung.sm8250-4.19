# SukiSU / SUSFS integration for NotKernel

This is an experimental integration for the Samsung SM8250 4.19 tree.
The initial target is r8q. Successful compilation does not establish device
boot, root-manager compatibility, module compatibility or stability.

## Pinned inputs and attribution

| Component | Source revision | Use |
| --- | --- | --- |
| Kernel baseline | `e0a6f4ada8e929728925e3d40c7d2bcde3762af7` in this repository | Existing build scripts and Backslash build reference |
| SukiSU-Ultra | [`fbc67d004b3b68723e91dd86d50dead1120b4a9a`](https://github.com/SukiSU-Ultra/SukiSU-Ultra/commit/fbc67d004b3b68723e91dd86d50dead1120b4a9a) on `builtin` | Latest builtin checked 2026-10-27, UAPI 6 |
| SUSFS 2.1.0 port | [`5e4f1930c9022b79559f3d337ef59e75a5562037`](https://github.com/TheNoxS1d/susfs-kernel-4.19/commit/5e4f1930c9022b79559f3d337ef59e75a5562037) | `kernel_patches/50_add_susfs_in_kernel-4.19.patch` and its three source/header files |
| NoMount | [`d6cb7158b5a98a8168fa7bae191e23cbcfd38974`](https://github.com/maxsteeel/nomount/commit/d6cb7158b5a98a8168fa7bae191e23cbcfd38974) | Upstream development snapshot plus the local ART allocation patch |

SUSFS originates from [simonpunk/susfs4ksu](https://gitlab.com/simonpunk/susfs4ksu).
The selected 4.19 port is by TheNoxS1d and its upstream contributors. The port's
license is retained verbatim in [SUSFS-LICENSE](SUSFS-LICENSE); SukiSU's license
remains in its pinned submodule. Original NotKernel, LineageOS, Samsung and
NoMount credits and license notices are retained.

These inputs are intentionally fixed. Newer SukiSU/SUSFS revisions change the
hook interfaces and must not be substituted through `submodule update --remote`.
The driver identifies itself as `v4.2.1-fbc67d00-notkernel` with version code
41095. This is a locally adapted builtin snapshot. The companion APK is the
official [SukiSU v4.2.1-r2 Manager](https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases/tag/v4.2.1-r2),
which also uses UAPI 6. Matching the UAPI does not require matching the APK's
numeric build code.

## Local adaptations

The imported SUSFS hooks were adapted to this tree's `fs_context`, `faccessat2`,
`do_execveat_common`, `access_ok` and `mm_walk_ops` backports. Existing PowerHAL
`libperfmgr_redirect` handling and the privileged Android uname compatibility
workaround remain in place. SUSFS pagemap filtering walks all affected entries
in each buffered range. The inode predicates are parenthesized so negation and
short-circuit conditions also work with null inodes/mappings.

The root integration uses SukiSU's actual read, fstat, access, stat, exec,
setresuid, reboot and devpts interfaces. Its native input handler supplies the
safe-mode volume-key detection; no extra call to its empty legacy input hook is
added. The successful-exec hook installs the scoped su-session fd after
`exec_binprm` succeeds. The init-rc fstat hook now uses the driver's static key.
Rooted builds require KSU and SUSFS in the
resolved config. KPM, manual-su and debug mode are disabled. The standard `ksu`
variant does not request SELinux permissive mode.

`patches/sukisu/0001-adapt-builtin-driver-for-notkernel.patch` contains:

- Offline version metadata and removal of an unused generated-header dependency.
- A seccomp configuration guard and local ADB path comparisons compatible with
  the selected SUSFS port.
- User-pointer stat/faccessat handlers compatible with this VFS, retaining
  fault-safe path copies, the chroot guard and live root-policy checks.
- Compatibility with SUSFS 2.1 task markers and omission of the newer optional
  priority-UID command, which this port does not implement.
- The existing authorized-app devpts relabel hook and synchronous SUSFS 2.1
  path-loop operation under cached KSU credentials, including restoration of
  the caller's credentials. The newer SUSFS worker object is not available in
  this port.
- Removal of unused unavailable headers and version guards for SELinux hiding
  hooks supported only on newer kernels.
- Explicitly disabled built-in preinit runner: this tree has no matching init
  hook, so the driver must not advertise preinit support based on installed
  headers alone.
- Explicitly unavailable optional CPU-spoof extension. Its newer clocksource,
  vDSO, HWCAP-array and CPU-erratum assumptions do not match this 4.19 tree.
  It is not registered or reported as supported, and its IO entry returns
  `-EOPNOTSUPP` before any writes. Core root/Manager communication does not
  depend on this extension.

The package-list bounds/allocation and root-grant revocation fixes are present
in the new upstream pin and no longer need backport hunks.

The preparation script verifies the SukiSU commit, applies the patch once and
rejects conflicts. The expected modified submodule and patch checksum appear
in build metadata. The `ksu` command remains compatible with existing usage;
rooted ZIP filenames now explicitly include `sukisu-susfs`.

`0002-initialize-legacy-susfs-sids.patch` populates the separate SUSFS domain
SID cache after the legacy policy write lock is released and the AVC is reset.
The upstream pre-5.10 path omitted this step. The core KSU cache's
`Cached zygote SID` message does not initialize the SUSFS cache. Without it,
the zygote/setresuid hook, manager fd installation, mount tagging and sdcard
monitor cannot recognize the relevant SELinux domains.

`0003-retain-android-boot-errors.patch` adds an optional `KSU_BOOT_LOG` setting,
enabled temporarily in this branch's `ksu.config`. It starts logcat asynchronously
before module scripts and stops it when `sys.boot_completed=1`. Warnings, errors
and crash messages from Android's main/system/crash buffers are written to
`/data/adb/notkernel-boot/android.log` and its rotated `.1` file. The previous
boot's pair is kept as `android.previous.log` and `android.previous.log.1`.
Each pair uses approximately 4 MiB at most; the directory is root-only (`0700`).
This setting is separate from KSU debug mode and does not change SELinux mode
or disable modules. Turn it off after boot validation.

## Verification

The previous April SukiSU pin, before this update, was built with the r8q `ksu`
configuration and default 300 MHz UFS profile
through ThinLTO, modpost and the final kernel link, producing `Image.gz` and
`dtbo.img`. This used Neutron Clang 24.0.0git, LLVM revision
`f42c87ba2c70219b1f4ad1f031a5b6a1ea6603fb`, from catalogue release `06092026`.
The linker emitted its existing conservative `--icf=safe` address-significance
warning; the build exited successfully.

The host regression suite covers build/packaging failure handling, resolved
configuration checks, both patch preparers, actual NoMount ART code under
allocation failures, SUSFS inode predicates and the actual SukiSU sucompat
handler under a simulated grant/revoke policy. New checks compile the UAPI
header to confirm version 6 and GET_INFO `0x80104b02`, and exercise the successful
exec requirement for su-session fd installation. The C harnesses use address and
undefined-behavior sanitizers. Policy and kernel services in the sucompat
harness are mocks; this is not an Android integration test.

At the previous pin, the changed VFS/proc, reboot, uname and SELinux objects also compiled separately
with the stock configuration and KSU/SUSFS disabled. The optional UFS 333 MHz driver/DT profile
has build-time verification only. Its details are in the root README.

Those older build results do not validate this update. The isolated
`validate-sukisu.yml` workflow builds this revision and uploads its logs and
artifacts; check its result before device testing. Termux installation steps
are in [termux.md](termux.md); the phone workflow itself still needs validation
on a real device.

## First device test

The 2026-10-27 device report for `4.19.325:Iowa/8e1d1f0d` shows repeated
zygote/SystemServer starts followed by Samsung bootchecker rescue reboots,
without a kernel panic. The supplied dmesg/logcat were captured in recovery;
they do not contain Android's fatal error. The SID initialization defect is
confirmed in source, but its role in that bootloop is not established. The next
device test must verify boot; a successful build alone does not resolve this.

If it loops again, collect `/data/adb/notkernel-boot/android*` from recovery
alongside `last_kmsg` (with `/data` decrypted). These are the Android boot logs,
unlike running `logcat` after starting recovery. Logs may contain app details;
only the relevant error excerpt is needed. After a successful boot, confirm
`sid ... is set for secctx_name 'u:r:zygote:s0'` and `'u:r:ksu:s0'` in dmesg,
then check Manager fd installation as described below.

Build `JOBS=12 UFS_AXI_MHZ=300 ./build-local.sh r8q ksu` first. Keep a known
working boot/kernel backup. With the matching Manager and modules initially
disabled, check boot, root grant and revoke, SELinux mode, safe mode, reboot,
suspend/resume, Wi-Fi, mobile data, camera and storage. Then enable the existing
modules individually, including NoMount and any SUSFS companion tool.

After boot, capture dmesg and logcat while opening the Manager. Check for
`GET_INFO = 0x80104b02` and `install fd for manager: <manager uid>` in dmesg,
and confirm logcat has no `UAPI version mismatch`. Exercise a fresh `su` grant
and a revoked grant as well. If `unsupported command` or preview mode remains,
keep the new logs together with the ZIP's build-info and config.

SUSFS rules and NoMount rules are distinct and may affect the same paths.
Investigate conflicts with each feature disabled separately. This integration
does not install companion modules, promise app-attestation results or establish
a performance gain. Only compare the optional UFS overclock after the updated
300 MHz build works reliably on the target ROM.
