#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose -p bdc-knowledge-farm-test -f farm-service/tests/compose.yaml)
trap '"${compose[@]}" down' EXIT
"${compose[@]}" up -d --wait postgres kafka
"${compose[@]}" run --rm farm-tests &
farm_pid=$!
"${compose[@]}" run --rm auth-tests &
auth_pid=$!
status=0
wait "$farm_pid" || status=1
wait "$auth_pid" || status=1
exit "$status"
