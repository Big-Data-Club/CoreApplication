# Knowledge Farm service

Go HTTP service on port 8087. Owns game state, server-graded harvest challenges
and a transactional reward outbox. PostgreSQL required; Kafka publishes
`farm.harvest.reward.v1` for Java Auth to credit `User.totalScore`.

See [feature/API/operations guide](../docs/features/KNOWLEDGE_FARM.md).

Required config: `JWT_SECRET`, `FARM_EVENT_SECRET` (both >=32 bytes),
`KAFKA_BROKERS`, `LMS_SERVICE_URL`, `AI_SERVICE_SECRET` (existing shared service
credential), and either `FARM_DATABASE_URL` or the PostgreSQL `PGHOST`,
`PGDATABASE`, `PGUSER`, `PGPASSWORD` variables. Use TLS outside local Compose.
`PORT` defaults to 8087. Database pool is capped at 10 connections.

`internal/farm/schema.sql` is the initial additive schema, applied under a
transaction advisory lock at startup. Subsequent schema changes must be new
forward-only migrations; do not repurpose deployed columns.

```bash
go test -race ./...
go run ./cmd/api
```

Set `FARM_TEST_DATABASE_URL` only to a disposable PostgreSQL database to enable
integration tests; they truncate the farm test tables. The repository script
`bash scripts/test-knowledge-farm.sh` creates an isolated test database and
runs both Go and Java tests without mounting application credentials.
