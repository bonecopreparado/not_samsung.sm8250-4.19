#!/usr/bin/env bash
# Apply this kernel's reviewed SukiSU compatibility fixes to the exact pin.
set -Eeuo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
expected=624727d1077f5afea894f066bcb8ca70079cf802
if [[ $(git -C KernelSU rev-parse HEAD) != "$expected" ]]; then
    printf 'Error: SukiSU must be at %s before applying patches.\n' "$expected" >&2
    exit 1
fi

for patch in "$PWD"/patches/sukisu/*.patch; do
    if git -C KernelSU apply --reverse --check "$patch" 2>/dev/null; then
        continue
    fi
    if ! git -C KernelSU apply --check "$patch"; then
        printf 'Error: SukiSU patch conflicts with the checkout: %s\n' "$patch" >&2
        exit 1
    fi
    git -C KernelSU apply "$patch"
done
