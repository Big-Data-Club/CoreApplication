#!/bin/sh
set -eu
# Suppress psql diagnostics because failed SQL can contain role passwords.
# Stage names identify the failing operation without exposing credentials.
run_sql() {
  stage="$1"
  file="$2"
  echo "Starting $stage"
  if ! psql -X -q -v ON_ERROR_STOP=1 -f "$file" >/dev/null 2>&1; then
    echo "FAILED: $stage. Check connectivity, role privileges and migration checksum; credentials/SQL suppressed." >&2
    exit 1
  fi
  echo "Completed $stage"
}
run_sql 'create gamefarm database and application role (requires CREATEDB/CREATEROLE)' /migrations/provision.sql
run_sql 'Auth reward receipts migration' /migrations/auth.sql
export PGDATABASE=gamefarm PGUSER="$FARM_DB_USER" PGPASSWORD="$FARM_DB_PASSWORD"
run_sql 'gamefarm migrations using application role' /migrations/farm.sql
