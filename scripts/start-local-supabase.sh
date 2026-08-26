#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
signing_key_path="${repository_root}/supabase/.temp/signing_keys.json"

if [[ ! -s "${signing_key_path}" ]]; then
  mkdir -p "$(dirname "${signing_key_path}")"
  printf '[]\n' >"${signing_key_path}"
  "${repository_root}/node_modules/.bin/supabase" gen signing-key \
    --algorithm ES256 \
    --append \
    --workdir "${repository_root}"
  chmod 600 "${signing_key_path}"
fi

"${repository_root}/node_modules/.bin/supabase" start --workdir "${repository_root}"
