# Consolidated schema: auth-and-management-service

Start with [`current.sql`](current.sql). This single file contains the final
columns, table constraints, indexes, functions, triggers and repository seed
defaults reconstructed from this service's SQL. It is not a concatenation of
CREATE/ALTER steps, and it is not a dump of a live Neon database.

Tables covered: `farm_score_receipts`, `tenant_sites`.

Auth snapshot covers `farm_score_receipts` and `tenant_sites` only. The Auth base schema is owned by JPA and must already provide `organizations`; it is not replaced by a placeholder table. The placeholder used during verification was excluded from this file.

The historical patches remain in [`migrations/releases`](../migrations/releases/)
for deployed ledgers, audit and rollback compatibility. Existing deployments
continue to use that history; startup does not execute `schema/current.sql`.
Lab, Chat and Workspace snapshots also record the covered original migration
names so startup does not replay the baseline after a fresh installation.

## Inspect or regenerate

From the Core repository root, with Docker available:

```sh
python3 scripts/build-sql-snapshots.py --service auth-and-management-service
python3 scripts/build-sql-snapshots.py --service auth-and-management-service --check
python3 scripts/check-sql-releases.py
```

The generator creates isolated PostgreSQL 17 databases in a temporary container,
replays repository inputs, normalizes the resulting DDL and checks a second
restoration. It reads no production connection settings and stops its own
container afterwards. `manifest.json` records input hashes and the output hash.
Only regenerate the affected service to avoid unrelated seed timestamp changes.

This Auth file is a reference for SQL-managed additions, not a replacement for
JPA schema generation. Do not apply it over an existing Auth database or use the
generic empty-database bootstrap command: `tenant_sites` requires the Auth-owned
`organizations` base table, and JPA may already create the auxiliary tables.
Use the existing Auth rollout and forward migrations when deploying changes.
