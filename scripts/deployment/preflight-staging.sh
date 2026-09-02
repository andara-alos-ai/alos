#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compose_file="$repository_root/infra/compose/compose.staging.yaml"
environment_file="${1:-/etc/alos/alos.staging.env}"

if [[ ! -r "$environment_file" ]]; then
  echo "Staging environment file tidak dapat dibaca: $environment_file" >&2
  exit 1
fi

if grep -Eq 'REPLACE_WITH|SET_ON_VPS_ONLY|example\.com' "$environment_file"; then
  echo "Staging environment masih memuat placeholder. Deployment dibatalkan." >&2
  exit 1
fi

docker compose --env-file "$environment_file" -f "$compose_file" config --quiet
echo "Preflight staging PASS."
