# SukiSU / SUSFS integration for NotKernel

This is an experimental integration for the Samsung SM8250 4.19 tree.
The initial target is r8q. Successful compilation does not establish device
boot, root-manager compatibility, module compatibility or stability.

## Pinned inputs and attribution

| Component | Source revision | Use |
| --- | --- | --- |
| Kernel baseline | `e0a6f4ada8e929728925e3d40c7d2bcde3762af7` in this repository | Existing build scripts and Backslash build reference |
| SukiSU-Ultra | [`624727d1077f5afea894f066bcb8ca70079cf802`](https://github.com/SukiSU-Ultra/SukiSU-Ultra/commit/624727d1077f5afea894f066bcb8ca70079cf802) on `builtin` | Built-in non-GKI root driver, 4.1.2-era interface |
| SUSFS 2.1.0 port | [`5e4f1930c9022b79559f3d337ef59e75a5562037`](https://github.com/TheNoxS1d/susfs-kernel-4.19/commit/5e4f1930c9022b79559f3d337ef59e75a5562037) | `kernel_patches/50_add_susfs_in_kernel-4.19.patch` and its three source/header files |
| NoMount | [`d6cb7158b5a98a8168fa7bae191e23cbcfd38974`](https://github.com/maxsteeel/nomount/commit/d6cb7158b5a98a8168fa7bae191e23cbcfd38974) | Upstream development snapshot plus the local ART allocation patch |

SUSFS originates from [simonpunk/susfs4ksu](https://gitlab.com/simonpunk/susfs4ksu).
The selected 4.19 port is by TheNoxS1d and its upstream contributors. The port's
license is retained verbatim in [SUSFS-LICENSE](SUSFS-LICENSE); SukiSU's license
remains in its pinned submodule. Original NotKernel, LineageOS, Samsung and
NoMount credits and license notices are retained.

These inputs are intentionally fixed. Newer SukiSU/SUSFS revisions change the
hook interfaces and must not be substituted through `submodule update --remote`.
The driver identifies itself as `v4.1.2-624727d1-notkernel` with compatibility
version code 40545. This is a locally adapted builtin snapshot, not an upstream
release binary. The initial companion APK is the official
[SukiSU v4.1.2 Manager](https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases/tag/v4.1.2).

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
added. Rooted builds require KSU, LSM hooks, manual hooks and SUSFS in the
resolved config. KPM, manual-su and debug mode are disabled. The standard `ksu`
variant does not request SELinux permissive mode.

`patches/sukisu/0001-adapt-builtin-driver-for-notkernel.patch` contains:

- Offline version metadata and removal of an unused generated-header dependency.
- A seccomp configuration guard and local ADB path comparisons compatible with
  the selected SUSFS port.
- The package-list bounds fix from SukiSU commit
  [`c6d2bb9`](https://github.com/SukiSU-Ultra/SukiSU-Ultra/commit/c6d2bb9a9f6e56b75b791c002482f15ac984b53e)
  by Kamenta and allocation-context fix from
  [`8c74411`](https://github.com/SukiSU-Ultra/SukiSU-Ultra/commit/8c74411cb713be2e106b2f15f3c4bf5f02274efd)
  by Wang Han.
- A root-grant check after the init-specific exec handling, following the
  revocation fix in ShirkNeko's
  [`03079cc`](https://github.com/SukiSU-Ultra/SukiSU-Ultra/commit/03079cccc9910624344d69d544bc2dcc7235f5fe).
  This takes the authorization fix without changing the boolean-hook ABI to
  the later SUSFS interface.

The preparation script verifies the SukiSU commit, applies the patch once and
rejects conflicts. The expected modified submodule and patch checksum appear
in build metadata. The `ksu` command remains compatible with existing usage;
rooted ZIP filenames now explicitly include `sukisu-susfs`.

## Verification

The r8q `ksu` configuration with the default 300 MHz UFS profile was built
through ThinLTO, modpost and the final kernel link, producing `Image.gz` and
`dtbo.img`. This used Neutron Clang 24.0.0git, LLVM revision
`f42c87ba2c70219b1f4ad1f031a5b6a1ea6603fb`, from catalogue release `06092026`.
The linker emitted its existing conservative `--icf=safe` address-significance
warning; the build exited successfully.

Thirty host tests pass. They cover build/packaging failure handling, resolved
configuration checks, both patch preparers, actual NoMount ART code under
allocation failures, SUSFS inode predicates and the actual SukiSU sucompat
handler under a simulated grant/revoke policy. The C harnesses use address and
undefined-behavior sanitizers. Policy and kernel services in the sucompat
harness are mocks; this is not an Android integration test.

The changed VFS/proc, reboot, uname and SELinux objects also compiled separately
with the stock configuration and KSU/SUSFS disabled. The optional UFS 333 MHz driver/DT profile
has build-time verification only. Its details are in the root README.

## First device test

Build `JOBS=12 UFS_AXI_MHZ=300 ./build-local.sh r8q ksu` first. Keep a known
working boot/kernel backup. With the matching Manager and modules initially
disabled, check boot, root grant and revoke, SELinux mode, safe mode, reboot,
suspend/resume, Wi-Fi, mobile data, camera and storage. Then enable the existing
modules individually, including NoMount and any SUSFS companion tool.

SUSFS rules and NoMount rules are distinct and may affect the same paths.
Investigate conflicts with each feature disabled separately. This integration
does not install companion modules, promise app-attestation results or establish
a performance gain. Only compare the optional UFS overclock after the updated
300 MHz build works reliably on the target ROM.
