#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${API_DATABASE_PASSWORD:-}" && -f "${repository_root}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${repository_root}/.env"
  set +a
fi

if [[ -z "${API_DATABASE_PASSWORD:-}" || "${API_DATABASE_PASSWORD}" == replace-with-* ]]; then
  echo "Set API_DATABASE_PASSWORD to a non-placeholder local value." >&2
  exit 1
fi

container_name="supabase_db_ai-customer-support-platform"

if ! docker inspect "${container_name}" >/dev/null 2>&1; then
  echo "Local Supabase database is not running. Run pnpm dev:supabase first." >&2
  exit 1
fi

docker exec \
  --env API_DATABASE_PASSWORD="${API_DATABASE_PASSWORD}" \
  --interactive \
  "${container_name}" \
  psql --username postgres --dbname postgres --set ON_ERROR_STOP=1 <<'SQL'
\getenv api_database_password API_DATABASE_PASSWORD
alter role api_login with login password :'api_database_password';
SQL

echo "Provisioned the local api_login password."
