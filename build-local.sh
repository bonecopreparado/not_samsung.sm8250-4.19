#!/usr/bin/env bash
set -Eeuo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source scripts/not-build-common.sh

# Arguments also allow unattended local builds without changing the CI default.
(( $# <= 2 )) || die 'Usage: ./build-local.sh [device] [stock|ksu|ksu+permissive]'
model_choice=${1:-}
add_choice=${2:-}
if [[ -z "$model_choice" ]]; then
    printf 'Available devices: %s\n' "${VALID_MODELS[*]}"
    read -r -p 'Device: ' model_choice
fi
if [[ -z "$add_choice" ]]; then
    printf 'Variants: stock, ksu, ksu+permissive\n'
    read -r -p 'Variant: ' add_choice
fi

build_kernel "${model_choice,,}" "${add_choice,,}" Image.gz
