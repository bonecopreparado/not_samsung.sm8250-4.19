#!/usr/bin/env bash
set -Eeuo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source scripts/not-build-common.sh

# Preserve the CI entry point and its KernelSU default.
[[ -n "${DEVICE:-}" ]] || die 'Set DEVICE, for example: DEVICE=r8q ./build.sh'
build_kernel "$DEVICE" "${BUILD_VARIANT:-ksu}" Image
