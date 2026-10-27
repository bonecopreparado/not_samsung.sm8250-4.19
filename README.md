# (not) Samsung SM8250 Kernel

## Building this fork

The build-script maintenance in this fork builds on the original work of
s-k-y.e and the other upstream contributors. It does not establish that a
particular ROM/device combination is tested.

For an ARM64 phone, follow the [Termux setup guide in Portuguese](Documentation/notkernel/termux.md)
to install Ubuntu and a native compiler from scratch. The automatic Neutron
download is for Linux x86_64 hosts; the phone instructions use `TC_DIR=/usr`.

On Ubuntu, install the host dependencies before building:

```sh
sudo apt install build-essential bc bison flex libssl-dev libelf-dev \
    git curl jq zstd zip unzip python3 cpio rsync \
    gcc-aarch64-linux-gnu gcc-arm-linux-gnueabi
```

Use Bash on Linux. GNU coreutils/findutils and util-linux (including `flock`)
are also required and are normally installed on Ubuntu. The scripts update
the pinned Git submodules needed by the selected variant automatically.
`stock` downloads Baseband-guard and NoMount and explicitly disables KernelSU.
It also works when the KernelSU repository is unavailable. The `ksu` variants
still require the pinned KernelSU source; they fail rather than silently
producing a build without root. Dependency downloads never ask for credentials.

### SukiSU and SUSFS integration

Rooted variants use [SukiSU-Ultra's builtin driver](https://github.com/SukiSU-Ultra/SukiSU-Ultra/commit/fbc67d004b3b68723e91dd86d50dead1120b4a9a),
pinned at `fbc67d004b3b68723e91dd86d50dead1120b4a9a` (latest `builtin` checked on
2026-10-27), with UAPI 6 for the v4.2.1-r2 Manager.
The kernel contains the [SUSFS 2.1.0 port for 4.19](https://github.com/TheNoxS1d/susfs-kernel-4.19/commit/5e4f1930c9022b79559f3d337ef59e75a5562037),
adapted to this tree's VFS backports. SUSFS stays at 2.1.0; the compatibility
patch adapts the newer driver to that interface. KPM, manual-su and debug mode
are disabled. Normal `ksu` builds retain SELinux enforcing.

The build applies `patches/sukisu/*.patch` to the exact SukiSU pin. These patches
make version generation offline, handle this tree's disabled seccomp configuration,
and preserve the 4.19 user-path and SUSFS interfaces. Package-list and root-grant
revocation fixes are now upstream. The scripts require built-in KSU and SUSFS,
and reject accidental enabling of KPM/debug/manual-su. Removed LSM/manual-hook
config symbols are no longer requested or checked.
The optional new CPU-spoof extension and preinit runner are unavailable in
this legacy integration; their required interfaces do not match this tree.
See [integration notes](Documentation/notkernel/sukisu-susfs.md) for sources,
local changes and validation scope.

Use the [official v4.2.1-r2 Manager APK](https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases/download/v4.2.1-r2/SukiSU_v4.2.1-r2_41068-release.apk)
for the initial test. The build does not install or update apps or modules on
the phone. Recheck root grants after replacing the Backslash Manager. Start
with modules disabled, then test modules one at a time. SUSFS support alone
does not configure hiding rules or guarantee compatibility with an app.
Any companion SUSFS tools must support the pinned 2.1.0 kernel interface.

The previous `e0a6f4ad` Backslash build completed on the maintainer's Ubuntu host
and a tester reported booting OneUI 8.5 on r8q. That result does not validate
the SukiSU/SUSFS, NoMount or clock changes in this branch.

After checking out the updated kernel branch, the scripts synchronize cached
submodule URLs and fetch the recorded commits automatically. For manual builds:

```sh
git submodule sync --recursive -- Baseband-guard NoMount KernelSU
GIT_TERMINAL_PROMPT=0 git submodule update --init --recursive -- Baseband-guard NoMount KernelSU
bash scripts/prepare-nomount.sh
bash scripts/prepare-sukisu.sh
```

If reusing a checkout prepared with the old `624727d1` pin, reverse its old
compatibility patch **before pulling this update**, while that old patch is
still checked out:

```sh
git -C KernelSU apply --reverse --check "$PWD/patches/sukisu/0001-adapt-builtin-driver-for-notkernel.patch"
git -C KernelSU apply --reverse "$PWD/patches/sukisu/0001-adapt-builtin-driver-for-notkernel.patch"
```

Only run the second command if the check succeeds. Preserve any additional
local edits and resolve conflicts before updating the submodule; a fresh clone
can also be used with the Termux instructions.

Do not use `git submodule update --remote` to reproduce this version. Retain the
tracked symlinks `drivers/kernelsu`, `security/baseband-guard` and `fs/nomount`.
Patched submodules intentionally appear modified; repeat preparation is safe
and conflicts stop the build without discarding local changes. Before switching
back to an older branch, reverse this branch's SukiSU patch from the repository
root with `git -C KernelSU apply --reverse "$PWD/patches/sukisu/0001-adapt-builtin-driver-for-notkernel.patch"`.
Stop if it conflicts, then switch branches and update submodules normally.

### NoMount update and local fixes

NoMount is pinned to [upstream dev commit d6cb7158](https://github.com/maxsteeel/nomount/commit/d6cb7158b5a98a8168fa7bae191e23cbcfd38974),
22 commits after the previous `9122a0bf` pin. The two commits after upstream
`master` provide explicit SRCU initialization and dentry-cache invalidation
fixes. This is a development snapshot, not a newly tagged stable release.
It also includes upstream changes to rule lookup/removal, directory lifetimes
and batched clearing. No device performance gain is assumed from those changes.

The build applies `patches/nomount/*.patch` through `scripts/prepare-nomount.sh`.
The local fixes check ART allocations, propagate errors before publishing
rules, clean up partially constructed directory topology, and allow the
child counter to represent all 256 entries. Patch application is idempotent
and refuses conflicting local edits or a different upstream commit.

The patched NoMount checkout intentionally appears modified in `git status`;
the committed patch series and its hashes in the build metadata describe those
changes. Keep additional edits separate when reproducing a build. For manual
kernel builds, run `bash scripts/prepare-nomount.sh` after submodule setup.
If switching back to an older kernel branch, first reverse this branch's patch
with `git -C NoMount apply --reverse "$PWD/patches/nomount/0001-handle-art-allocation-failures.patch"`;
stop if it conflicts, then switch branches and update the submodules normally.

For NoMount module tests, use userspace/metamodule built from the same pinned
upstream revision. This change does not update modules already installed on
the phone. Check rule addition/removal and exclusions after the update.

### Build commands

```sh
# Interactive device/variant selection:
./build-local.sh

# S20 FE (r8q), with KernelSU explicitly disabled:
JOBS=12 ./build-local.sh r8q stock

# SukiSU + SUSFS, keeping the existing ksu command:
JOBS=12 ./build-local.sh r8q ksu

# Existing CI entry point: SukiSU + SUSFS by default, uncompressed Image:
DEVICE=r8q JOBS=12 ./build.sh
```

`build-local.sh` keeps its compressed `Image.gz` output. `build.sh` keeps
its uncompressed `Image` output and accepts `BUILD_VARIANT=stock`, `ksu`
or `ksu+permissive`. The last variant explicitly enables the existing
SELinux permissive configuration; use `stock` or `ksu` for ordinary testing.
`stock` means KernelSU is disabled and no permissive fragment is added, not a Samsung
stock kernel. `JOBS` defaults to the CPUs available to the current process.
Both scripts can be called from another working directory.

### Experimental UFS AXI profile for r8q

The default remains **300 MHz**. To compare the same source at both profiles:

```sh
JOBS=12 UFS_AXI_MHZ=300 ./build-local.sh r8q ksu
JOBS=12 UFS_AXI_MHZ=333 ./build-local.sh r8q ksu
```

`333` enables `CONFIG_R8Q_UFS_AXI_333MHZ` and requests **333,333,333 Hz on
GCC_UFS_PHY_AXI_CLK**. The clock table uses the existing 600 MHz GPLL0 with
an M/N divider of 5/9; the shared PLL is not retuned. The DT maximum and
clock driver's voltage limits are changed together. The new frequency votes
for **VDD_HIGH**, which can increase power consumption and heat. UFS UniPro,
ICE and device reference clocks remain unchanged. This is an AXI-bus experiment,
not a verified 333 MHz setting for every UFS clock or a storage-throughput claim.

This profile has not been validated on hardware. Storage overclocking can cause
I/O errors or data corruption: back up data and keep the tested kernel available
before flashing an experimental build. Validate the updated 300 MHz build first.
Then compare boot, suspend/resume, temperature and storage read/write integrity
with the same ROM, modules, compiler and AnyKernel3 revision. Stop testing the
OC profile if UFS resets/timeouts, I/O errors or corrupted files occur. Benchmark
only ordinary test files; do not write directly to block devices.

The build rejects `333` for other devices and checks the resolved configuration.
Selecting `300` again explicitly disables the option, including incremental
builds. ZIP names contain `ufs300` or `ufs333`, and the profile is recorded in
the build metadata. Rooted ZIPs are labeled `sukisu-susfs`; the build info also
records the root provider, SUSFS version and both patch hashes. Neither profile
is automatically flashed.

Every successful build leaves a uniquely named ZIP in the repository root,
plus `.zip.sha256`, `.zip.config` and `.zip.build-info.txt` sidecars. The
checksum file covers the ZIP and both metadata files. Verify it with
`sha256sum -c <filename>.zip.sha256` from the repository root. The build info
records the source commit, tracked dirty state, submodule commits, AnyKernel3
commit, compiler version and boot artifact hashes. Keep these files together.
Additional dirty source changes themselves are not captured; commit changes
before making a release. The expected NoMount and SukiSU patch series is committed in
the parent kernel repository as described above.

The scripts stop on failed commands or missing/empty boot artifacts. They
rebuild boot outputs while keeping other compiled objects, preserve existing
ZIPs and any local AnyKernel3 checkout, and reject simultaneous builds in the
same checkout. Existing release workflows remain manual and retain their
own publication behavior.

The separate `Validate r8q SukiSU` workflow runs host tests and an enforcing
300 MHz build for pull requests targeting `codex/r8q-sukisu-susfs`, or manually.
It uploads build artifacts and logs without publishing a release. A successful
host test run alone does not establish that the kernel builds or boots.

### Toolchain and packaging inputs

`TC_DIR` selects an existing Clang installation; the default is `tc/clang`.
An incomplete existing directory causes an error instead of silently falling
back to the host compiler. Move that directory aside or choose another
`TC_DIR` to retry. A failed new download does not create the toolchain cache.

For convenience, the first unpinned download still resolves the latest
Neutron release. Its exact archive URL and SHA-256 are recorded. For a later
build, supply that URL as `CLANG_URL` and that checksum as `CLANG_SHA256`;
both values are required together and mismatches stop the build. Use a new
`TC_DIR` when switching versions. A preinstalled toolchain without recorded
archive provenance is identified as such in the build info.

Set `AK3_COMMIT` to a full commit SHA to select a specific AnyKernel3 revision
for the device branch. By default the device branch is resolved at build time
and the selected commit is recorded. Save/pin both external inputs along with
the source and config before comparing builds. Pinning inputs alone does not
guarantee byte-identical kernels; build timestamps and host tools also matter.

### Build-script regression checks

```sh
bash -n build.sh build-local.sh scripts/not-build-common.sh scripts/prepare-nomount.sh scripts/prepare-sukisu.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The build-script tests use simulated compiler/make output and a local packaging
fixture. With the pinned NoMount submodule initialized, the NoMount tests also
verify real patch application and compile its ART code in a host harness using
GCC's address/undefined-behavior sanitizers. They cover allocation failures at
all five ART allocation sites, 256-way branching, UID chains and 15,000 repeated
insert/remove operations. They do not test VFS concurrency, compile a full kernel
or boot a phone. In tracing environments where LeakSanitizer cannot run, use
`ASAN_OPTIONS=detect_leaks=0`; the harness still checks its ART allocation count.
Hardware testing on the target ROM is required before calling a build stable.

# Introduction
- This repository is always compliant with the latest LineageOS common sm8250 kernel changes.
- All branches are prone to force push, with the sole exception of `lineage-23.2`

## Warning:
- The kernel source code is **always** under development and may cause some unpredictable problems.
- **You are being warned.**
- Credit me if you use this source for any of your projects.
- Please use it with caution.

## Warranty
- None, none at all. I am handing you a **sharp knife**, it is not on me if you stab yourself with it.
- no warranties.
- no support.
- not.

## Notes
- This kernel is combining contributions from multiple upstreams to make it as practical and well-rounded as possible.
- Code required for OneUI support was selectively cherry-picked from various sources.
- Support for all the remaining Samsung SM8250 devices is available in the source, however it probably needs some work to get it refined.
- I (s-k-y.e) support all the roms available for r8q, from Android 11 up to Android 17 QPR0, with OneUI support starting in Android14.
- Some users says that it also works fine in Android13/OneUI5.1, however that's unsupported.

## Telegram
- [t.me/not_kernel](https://t.me/not_kernel)
- [t.me/not_kernelbuilds](https://t.me/not_kernelbuilds)

## Engineered to perfection.
