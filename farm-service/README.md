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

Game code is grouped by responsibility in `internal/game`: `*_handler.go`
defines HTTP endpoints, `*_repository.go` owns transactional PostgreSQL
operations, `*_service.go` owns gameplay and learning rules, and `world_rules.go`
holds shared domain calculations. `dto/` defines request contracts;
`repository/learning_outbox.go` claims LMS attempt deliveries without holding a
database connection during the remote HTTP call. Keep all coin, inventory,
harvest and reward mutations inside one `withGame` transaction. When adding a
feature, put validation in the service layer and persistence behind repository
functions so retries cannot apply it twice.

The per-farm row lock serializes changes to one player's farm while independent
farms can run concurrently. Multiple service replicas may consume the LMS and
reward outboxes; `SKIP LOCKED` leases and stable challenge/event IDs make replay
safe. Capacity is bounded by the database pool, transaction duration, and LMS/
Kafka latency. Monitor pool wait time, transaction latency, outbox backlog and
API p95 before increasing replicas or the connection cap. Avoid remote calls
inside game transactions. State reads currently tick the farm in a write
transaction; a dedicated read projection/cache is the next scaling step if
state polling becomes the bottleneck.

`internal/farm/schema.sql` and `internal/game/schema.sql` are additive schemas
applied under a transaction advisory lock at startup. Forward-only SQL changes
are recorded in `migrations/`. Care timer V004 adds a per-farm version; existing
farms receive one 12-hour care refill lazily on their first request after
rollout, so startup does not rewrite all farms or require a manual DB command.

```bash
go test -race ./...
go run ./cmd/api
```

Set `FARM_TEST_DATABASE_URL` only to a disposable PostgreSQL database to enable
integration tests; they truncate the farm test tables. The repository script
`bash scripts/test-knowledge-farm.sh` creates an isolated test database and
runs both Go and Java tests without mounting application credentials.
