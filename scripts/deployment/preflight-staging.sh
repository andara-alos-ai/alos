#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
environment_file="${1:-/etc/alos/alos.staging.env}"
python_bin="${ALOS_PYTHON_BIN:-$repository_root/.venv/bin/python}"
deployment_mode="${ALOS_DEPLOYMENT_MODE:-compose}"

if [[ ! -r "$environment_file" ]]; then
  echo "Staging environment file tidak dapat dibaca: $environment_file" >&2
  exit 1
fi

if grep -Eq 'REPLACE_WITH|SET_ON_VPS_ONLY|example\.com' "$environment_file"; then
  echo "Staging environment masih memuat placeholder. Deployment dibatalkan." >&2
  exit 1
fi

if [[ "$deployment_mode" == "compose" ]]; then
  compose_file="$repository_root/infra/compose/compose.staging.yaml"
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker Compose diperlukan untuk mode compose." >&2
    exit 1
  fi
  docker compose --env-file "$environment_file" -f "$compose_file" config --quiet
  echo "Preflight VPS Compose PASS."
  exit 0
fi

if [[ "$deployment_mode" != "native" ]]; then
  echo "ALOS_DEPLOYMENT_MODE harus compose atau native." >&2
  exit 1
fi

if [[ ! -x "$python_bin" ]]; then
  echo "Python virtual environment tidak ditemukan: $python_bin" >&2
  exit 1
fi

if [[ "$(stat -c '%a' "$environment_file")" -gt 640 ]]; then
  echo "Environment file harus dibatasi ke mode 0640 atau lebih ketat." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$environment_file"
set +a
export ALOS_ENVIRONMENT="${ALOS_ENVIRONMENT:-staging}"
export ALOS_WEB_ORIGIN="${ALOS_WEB_ORIGIN:-https://${ALOS_PUBLIC_HOST}}"
export ALOS_MIGRATIONS_PATH="${ALOS_MIGRATIONS_PATH:-$repository_root/infra/database}"
(cd "$repository_root/services/platform" && "$python_bin" -c 'from alos.config import get_settings; get_settings(); print("ALOS configuration valid")')
echo "Preflight VPS native PASS."
