# Consolidated schema: farm-service

Start with [`current.sql`](current.sql). This single file contains the final
columns, table constraints, indexes, functions, triggers and repository seed
defaults reconstructed from this service's SQL. It is not a concatenation of
CREATE/ALTER steps, and it is not a dump of a live Neon database.

Tables covered: `economy_ledger`, `entity_runtime`, `farm_answers`, `farm_economy`, `farm_inventory`, `farm_outbox`, `farm_states`, `farm_wild_insects`, `game_harvest_receipts`, `game_learning`, `game_learning_outbox`, `virtual_farms`, `world_entities`.

The historical patches remain in [`migrations/releases`](../migrations/releases/)
for deployed ledgers, audit and rollback compatibility. Existing deployments
continue to use that history; startup does not execute `schema/current.sql`.
Lab, Chat and Workspace snapshots also record the covered original migration
names so startup does not replay the baseline after a fresh installation.

## Inspect or regenerate

From the Core repository root, with Docker available:

```sh
python3 scripts/build-sql-snapshots.py --service farm-service
python3 scripts/build-sql-snapshots.py --service farm-service --check
python3 scripts/check-sql-releases.py
```

The generator creates isolated PostgreSQL 17 databases in a temporary container,
replays repository inputs, normalizes the resulting DDL and checks a second
restoration. It reads no production connection settings and stops its own
container afterwards. `manifest.json` records input hashes and the output hash.
Only regenerate the affected service to avoid unrelated seed timestamp changes.

For a deliberately empty PostgreSQL database, an operator can apply the file
with `psql -X -v ON_ERROR_STOP=1 --single-transaction -f farm-service/schema/current.sql`.
The operator must select the intended empty database through normal libpq
connection settings. Do not run this file against an existing Neon database.
New deployed changes still use forward migrations; after review, update this
consolidated representation through the generator.
