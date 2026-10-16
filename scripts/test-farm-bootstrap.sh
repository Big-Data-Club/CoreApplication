#!/usr/bin/env bash
# Disposable PostgreSQL; all credentials below are test-only.
set -euo pipefail
python3 -m unittest discover -s scripts/farm-bootstrap -p 'test_*.py'
test_dir=$(mktemp -d)
container="bdc-farm-bootstrap-test-${RANDOM}-$$"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  python3 - "$test_dir" <<'PY'
import shutil, sys
shutil.rmtree(sys.argv[1])
PY
}
trap cleanup EXIT
python3 - "$test_dir" <<'PY'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('bootstrap', 'scripts/bootstrap-knowledge-farm.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
out = pathlib.Path(sys.argv[1])
for name in ('provision.sql', 'run.sh'):
    (out / name).write_text((m.ROOT / 'scripts/farm-bootstrap' / name).read_text())
(out / 'auth.sql').write_text(m.migration_sql([m.ROOT / 'auth-and-management-service/migrations/V20261017__farm_score_receipts.sql']))
(out / 'farm.sql').write_text(m.migration_sql(sorted((m.ROOT / 'farm-service/migrations').glob('V*.sql'))))
PY
docker run -d --name "$container" --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=bootstrap_test -e POSTGRES_DB=auth_test \
  -e PGHOST=localhost -e PGUSER=postgres -e PGPASSWORD=bootstrap_test -e PGDATABASE=auth_test \
  -e FARM_DB_USER=gamefarm_app -e FARM_DB_PASSWORD=farm_test postgres:16-alpine >/dev/null
for attempt in {1..50}; do
  if docker exec "$container" pg_isready -h localhost -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
# Exercise CREATEDB/CREATEROLE without PostgreSQL superuser privileges.
docker exec "$container" psql -X -q -c "CREATE ROLE deploy_owner LOGIN CREATEDB CREATEROLE PASSWORD 'deploy_test'; ALTER DATABASE auth_test OWNER TO deploy_owner;" >/dev/null
docker cp "$test_dir/." "$container:/migrations"
docker exec -e PGUSER=deploy_owner -e PGPASSWORD=deploy_test "$container" sh /migrations/run.sh
docker exec -e PGUSER=deploy_owner -e PGPASSWORD=deploy_test "$container" sh /migrations/run.sh
# A dedicated application role owns the farm DB and all three game tables.
actual=$(docker exec "$container" psql -X -At -d gamefarm -c "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner='gamefarm_app' AND tablename IN ('farm_states','farm_answers','farm_outbox')")
[[ "$actual" == 3 ]]
actual=$(docker exec "$container" psql -X -At -d auth_test -c 'SELECT count(*) FROM farm_deploy_migrations')
[[ "$actual" == 1 ]]
# Changed migration must stop before rollout and must not overwrite its receipt.
docker exec "$container" psql -X -q -d gamefarm -c "UPDATE farm_deploy_migrations SET checksum='invalid'" >/dev/null
if docker exec -e PGUSER=deploy_owner -e PGPASSWORD=deploy_test "$container" sh /migrations/run.sh; then
  echo 'ERROR: migration checksum drift was accepted' >&2
  exit 1
fi
echo 'PASS: bootstrap, repeat deploy, separate role/database and checksum drift rejection'
