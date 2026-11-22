# Consolidated schema: lab-service

Start with [`current.sql`](current.sql). This single file contains the final
columns, table constraints, indexes, functions, triggers and repository seed
defaults reconstructed from this service's SQL. It is not a concatenation of
CREATE/ALTER steps, and it is not a dump of a live Neon database.

Tables covered: `datasets`, `environment_templates`, `evidence_events`, `experiment_definitions`, `experiment_trials`, `experiment_variables`, `lab_datasets`, `lab_enrollments`, `lab_leaderboard`, `lab_runs`, `lab_runtime_task_attempts`, `lab_runtime_tasks`, `lab_section_content`, `lab_sections`, `lab_sessions`, `lab_submissions`, `lab_test_cases`, `lab_versions`, `labs`, `submission_test_results`, `users`, `workflow_edges`, `workflow_nodes`, `workspace_files`, `lab_schema_migrations`.

The historical patches remain in [`migrations/releases`](../migrations/releases/)
for deployed ledgers, audit and rollback compatibility. Existing deployments
continue to use that history; startup does not execute `schema/current.sql`.
Lab, Chat and Workspace snapshots also record the covered original migration
names so startup does not replay the baseline after a fresh installation.

## Inspect or regenerate

From the Core repository root, with Docker available:

```sh
python3 scripts/build-sql-snapshots.py --service lab-service
python3 scripts/build-sql-snapshots.py --service lab-service --check
python3 scripts/check-sql-releases.py
```

The generator creates isolated PostgreSQL 17 databases in a temporary container,
replays repository inputs, normalizes the resulting DDL and checks a second
restoration. It reads no production connection settings and stops its own
container afterwards. `manifest.json` records input hashes and the output hash.
Only regenerate the affected service to avoid unrelated seed timestamp changes.

For a deliberately empty PostgreSQL database, an operator can apply the file
with `psql -X -v ON_ERROR_STOP=1 --single-transaction -f lab-service/schema/current.sql`.
The operator must select the intended empty database through normal libpq
connection settings. Do not run this file against an existing Neon database.
New deployed changes still use forward migrations; after review, update this
consolidated representation through the generator.
