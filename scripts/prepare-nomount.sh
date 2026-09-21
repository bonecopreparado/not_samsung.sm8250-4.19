#!/usr/bin/env bash
# Apply the kernel's reviewed NoMount fixes without discarding local changes.
set -Eeuo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
expected=d6cb7158b5a98a8168fa7bae191e23cbcfd38974
if [[ $(git -C NoMount rev-parse HEAD) != "$expected" ]]; then
    printf 'Error: NoMount must be at %s before applying patches.\n' "$expected" >&2
    exit 1
fi

for patch in "$PWD"/patches/nomount/*.patch; do
    if git -C NoMount apply --reverse --check "$patch" 2>/dev/null; then
        continue
    fi
    if ! git -C NoMount apply --check "$patch"; then
        printf 'Error: NoMount patch conflicts with the checkout: %s\n' "$patch" >&2
        exit 1
    fi
    git -C NoMount apply "$patch"
done
