# (not) Samsung SM8250 Kernel

## Building this fork

The build-script maintenance in this fork builds on the original work of
s-k-y.e and the other upstream contributors. It does not establish that a
particular ROM/device combination is tested.

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

```sh
# Interactive device/variant selection:
./build-local.sh

# S20 FE (r8q), with KernelSU explicitly disabled:
JOBS=12 ./build-local.sh r8q stock

# KernelSU, using the same local build entry point:
JOBS=12 ./build-local.sh r8q ksu

# Existing CI entry point: KernelSU by default, uncompressed Image:
DEVICE=r8q JOBS=12 ./build.sh
```

`build-local.sh` keeps its compressed `Image.gz` output. `build.sh` keeps
its uncompressed `Image` output and accepts `BUILD_VARIANT=stock`, `ksu`
or `ksu+permissive`. The last variant explicitly enables the existing
SELinux permissive configuration; use `stock` or `ksu` for ordinary testing.
`stock` means KernelSU is disabled and no permissive fragment is added, not a Samsung
stock kernel. `JOBS` defaults to the CPUs available to the current process.
Both scripts can be called from another working directory.

Every successful build leaves a uniquely named ZIP in the repository root,
plus `.zip.sha256`, `.zip.config` and `.zip.build-info.txt` sidecars. The
checksum file covers the ZIP and both metadata files. Verify it with
`sha256sum -c <filename>.zip.sha256` from the repository root. The build info
records the source commit, tracked dirty state, submodule commits, AnyKernel3
commit, compiler version and boot artifact hashes. Keep these files together.
Dirty source changes themselves are not captured; commit changes before
making a release.

The scripts stop on failed commands or missing/empty boot artifacts. They
rebuild boot outputs while keeping other compiled objects, preserve existing
ZIPs and any local AnyKernel3 checkout, and reject simultaneous builds in the
same checkout. Existing release workflows remain manual and retain their
own publication behavior.

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
bash -n build.sh build-local.sh scripts/not-build-common.sh
python3 -m unittest discover -s tests -p 'test_not_build.py' -v
```

The tests use simulated compiler/make output and a local packaging fixture;
they do not download dependencies or compile/boot a kernel. Hardware testing
on the target ROM is still required before calling a build stable.

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
