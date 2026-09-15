#!/usr/bin/env bash
# Shared by build.sh and build-local.sh, which enable errexit and pipefail.

VALID_MODELS=(bloomxq c1q c2q f2q gts7l gts7lwifi gts7xl gts7xlwifi r8q x1q y2q z3q)

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

require_commands() {
    local command_name
    for command_name in "$@"; do
        command -v "$command_name" >/dev/null || die "Missing command: $command_name"
    done
}

prepare_toolchain() {
    local requested_url=${CLANG_URL:-} requested_sha=${CLANG_SHA256:-}
    local url archive_sha download_dir tool
    [[ -z "$requested_url" && -z "$requested_sha" ]] || {
        [[ -n "$requested_url" && "$requested_sha" =~ ^[[:xdigit:]]{64}$ ]] ||
            die 'Set both CLANG_URL and its 64-digit CLANG_SHA256.'
        requested_sha=${requested_sha,,}
    }

    if [[ ! -e "$TC_DIR" ]]; then
        require_commands curl tar zstd jq
        url=$requested_url
        if [[ -z "$url" ]]; then
            url=$(curl -fLsS --retry 3 \
                https://api.github.com/repos/Neutron-Toolchains/clang-build-catalogue/releases/latest |
                jq -er '[.assets[] | select(.name | endswith(".tar.zst")) | .browser_download_url][0] // empty')
        fi
        [[ -n "$url" ]] || die 'No Clang archive URL found.'
        download_dir="$BUILD_TMP/toolchain"
        mkdir -p "$download_dir/payload"
        curl -fLsS --retry 3 "$url" -o "$download_dir/clang.tar.zst"
        archive_sha=$(sha256sum "$download_dir/clang.tar.zst")
        archive_sha=${archive_sha%% *}
        [[ -z "$requested_sha" || "$archive_sha" == "$requested_sha" ]] ||
            die 'Clang archive SHA-256 mismatch.'
        tar --zstd -xf "$download_dir/clang.tar.zst" \
            -C "$download_dir/payload" --strip-components=1
        # Install the cache only after a complete download and usable extraction.
        for tool in clang ld.lld llvm-as llvm-ar llvm-nm llvm-objcopy llvm-objdump llvm-strip; do
            [[ -x "$download_dir/payload/bin/$tool" ]] || die "Clang archive is missing $tool."
        done
        "$download_dir/payload/bin/clang" --version >/dev/null
        printf 'clang_url=%s\nclang_archive_sha256=%s\n' "$url" "$archive_sha" \
            > "$download_dir/payload/.not-toolchain.txt"
        mkdir -p "$(dirname -- "$TC_DIR")"
        mv -- "$download_dir/payload" "$TC_DIR"
    elif [[ -n "$requested_url" ]]; then
        [[ -f "$TC_DIR/.not-toolchain.txt" ]] &&
            grep -Fxq "clang_url=$requested_url" "$TC_DIR/.not-toolchain.txt" &&
            grep -Fxq "clang_archive_sha256=$requested_sha" "$TC_DIR/.not-toolchain.txt" ||
            die 'Cached Clang does not match the requested pin; use a new TC_DIR.'
    fi

    for tool in clang ld.lld llvm-as llvm-ar llvm-nm llvm-objcopy llvm-objdump llvm-strip; do
        [[ -x "$TC_DIR/bin/$tool" ]] ||
            die "Incomplete toolchain: $TC_DIR/bin/$tool. Move it aside or set TC_DIR."
    done
    "$TC_DIR/bin/clang" --version >/dev/null
    export PATH="$TC_DIR/bin:$PATH"
}

build_kernel() {
    local device=$1 variant=$2 image=$3 valid=false model fragment
    local jobs=${JOBS:-$(nproc)} source_sha dirty=false
    local out="$PWD/out" boot dts dtb ak3 zipname toolchain_version ak3_sha
    local -a configs make_args dtbs
    for model in "${VALID_MODELS[@]}"; do
        [[ "$device" != "$model" ]] || valid=true
    done
    [[ "$valid" == true ]] || die "Unsupported device: $device"
    [[ "$jobs" =~ ^[1-9][0-9]*$ ]] || die 'JOBS must be a positive integer.'
    [[ -z "${AK3_COMMIT:-}" || "$AK3_COMMIT" =~ ^[[:xdigit:]]{40}$ ]] ||
        die 'AK3_COMMIT must be a full 40-digit commit SHA.'

    configs=(vendor/kona-perf_defconfig vendor/samsung/kona-sec-common.config
        "vendor/samsung/$device.config")
    case "$variant" in
        stock) ;;
        ksu) configs+=(vendor/not/ksu.config) ;;
        ksu+permissive) configs+=(vendor/not/ksu.config vendor/not/permissive.config) ;;
        *) die "Unsupported variant: $variant" ;;
    esac
    configs+=(vendor/not/localversion.config)
    for fragment in "${configs[@]}"; do
        [[ -f "arch/arm64/configs/$fragment" ]] || die "Missing config: $fragment"
    done
    require_commands git make zip unzip find sort sha256sum mktemp realpath flock
    mkdir -p "$out"
    # One output/cache tree must not be built concurrently by the two entry points.
    exec 9>"$out/.not-build.lock"
    flock -n 9 || die 'Another kernel build is using this checkout.'
    BUILD_TMP=$(mktemp -d "$PWD/.not-build.XXXXXX")
    trap 'rm -rf -- "$BUILD_TMP"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    TC_DIR=$(realpath -m -- "${TC_DIR:-$PWD/tc/clang}")
    prepare_toolchain

    git submodule update --init --recursive
    source_sha=$(git rev-parse --verify HEAD)
    [[ -z "$(git status --porcelain --untracked-files=no)" ]] || dirty=true
    export PROJECT_NAME="$device"
    export PLATFORM_VERSION="${PLATFORM_VERSION:-11}"
    make_args=("-j$jobs" "O=$out" ARCH=arm64 CC=clang LD=ld.lld AS=llvm-as
        AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump
        STRIP=llvm-strip CROSS_COMPILE=aarch64-linux-gnu-
        CROSS_COMPILE_ARM32=arm-linux-gnueabi- LLVM=1 LLVM_IAS=1)

    printf 'Building %s (%s) with %s jobs\n' "$device" "$variant" "$jobs"
    make "${make_args[@]}" "${configs[@]}"
    make "${make_args[@]}" olddefconfig

    boot="$out/arch/arm64/boot"
    dts="$boot/dts/vendor/qcom"
    # Discard boot artifacts from earlier builds, but retain compiled objects.
    rm -rf -- "$boot"
    make "${make_args[@]}" dtbo.img
    make "${make_args[@]}" "$image"
    [[ -s "$boot/$image" ]] || die "Missing or empty $image."
    [[ -s "$boot/dtbo.img" ]] || die 'Missing or empty dtbo.img.'
    [[ -d "$dts" ]] || die 'Device tree output directory is missing.'
    find "$dts" -type f -name '*.dtb' -print0 | LC_ALL=C sort -z > "$BUILD_TMP/dtbs.list"
    mapfile -d '' -t dtbs < "$BUILD_TMP/dtbs.list"
    (( ${#dtbs[@]} > 0 )) || die 'No DTBs were produced.'
    for dtb in "${dtbs[@]}"; do
        [[ -s "$dtb" ]] || die "Empty DTB: $dtb"
    done
    cat -- "${dtbs[@]}" > "$boot/dtb"
    [[ -s "$boot/dtb" ]] || die 'Combined DTB is empty.'
    [[ -s "$out/.config" ]] || die 'Final kernel configuration is missing.'

    # Package in a private directory; never delete the user's AnyKernel3 checkout.
    ak3="$BUILD_TMP/AnyKernel3"
    git clone -q --single-branch -b "$device" https://github.com/notkernel-oss/AnyKernel3 "$ak3"
    if [[ -n "${AK3_COMMIT:-}" ]]; then
        git -C "$ak3" fetch origin "$AK3_COMMIT"
        git -C "$ak3" checkout --detach "$AK3_COMMIT"
    fi
    ak3_sha=$(git -C "$ak3" rev-parse HEAD)
    [[ -s "$ak3/anykernel.sh" && -s "$ak3/tools/ak3-core.sh" &&
       -s "$ak3/META-INF/com/google/android/update-binary" ]] || die 'Incomplete AnyKernel3 template.'
    rm -f -- "$ak3"/Image* "$ak3/dtb" "$ak3/dtbo.img"
    cp -- "$boot/$image" "$boot/dtb" "$boot/dtbo.img" "$ak3/"

    # Unique filenames preserve prior builds, including retries on the same commit.
    zipname="not-${variant//+/-}-$(date -u '+%Y%m%d-%H%M%S')-${source_sha:0:8}-$device-${BUILD_TMP##*.}.zip"
    (cd "$ak3" && zip -qr9 "$BUILD_TMP/$zipname" . \
        -x '.git' '.git/*' '.gitignore' 'README.md' '*placeholder')
    unzip -tq "$BUILD_TMP/$zipname"
    toolchain_version=$("$TC_DIR/bin/clang" --version)
    {
        printf 'source_commit=%s\nsource_dirty=%s\ndevice=%s\nvariant=%s\n' \
            "$source_sha" "$dirty" "$device" "$variant"
        printf 'image=%s\njobs=%s\nplatform_version=%s\nanykernel_commit=%s\n' \
            "$image" "$jobs" "$PLATFORM_VERSION" "$ak3_sha"
        printf 'clang_version=%s\n' "${toolchain_version%%$'\n'*}"
        if [[ -f "$TC_DIR/.not-toolchain.txt" ]]; then
            cat "$TC_DIR/.not-toolchain.txt"
        else
            printf 'clang_source=preinstalled (archive provenance unavailable)\n'
        fi
        printf '\nSubmodules:\n'
        git submodule status --recursive
        printf '\nBuild artifact hashes:\n'
        (cd "$boot" && sha256sum "$image" dtb dtbo.img)
    } > "$BUILD_TMP/$zipname.build-info.txt"
    cp -- "$out/.config" "$BUILD_TMP/$zipname.config"
    (cd "$BUILD_TMP" && sha256sum "$zipname" "$zipname.config" \
        "$zipname.build-info.txt" > "$zipname.sha256")
    mv -- "$BUILD_TMP/$zipname" "$BUILD_TMP/$zipname.config" \
        "$BUILD_TMP/$zipname.build-info.txt" "$BUILD_TMP/$zipname.sha256" .
    printf 'Build complete: %s/%s\n' "$PWD" "$zipname"
}
