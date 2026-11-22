# Consolidated schemas and migration history

## Read the consolidated schema

Each service now exposes **one `schema/current.sql`** with the final table
columns, constraints, indexes and related objects. This is a reconstructed schema,
not a concatenation of historical ALTER statements and not a live Neon export.
Repository seed defaults are included; production data and API keys are not.

| Service | Consolidated SQL |
|---|---|
| LMS | [current.sql](../../lms-service/schema/current.sql) |
| AI | [current.sql](../../ai-service/schema/current.sql) |
| Lab | [current.sql](../../lab-service/schema/current.sql) |
| Chat | [current.sql](../../chat-service/schema/current.sql) |
| Farm | [current.sql](../../farm-service/schema/current.sql) |
| DutyLog | [current.sql](../../dutylog/backend/schema/current.sql) |
| Workspace | [current.sql](../../workspace-service/schema/current.sql) |
| Auth SQL-managed additions | [current.sql](../../auth-and-management-service/schema/current.sql) |
| Personalize / DuckDB | [current.sql](../../personalize-service/schema/current.sql) |

Auth's JPA-owned base tables are not defined in its historical SQL files. The
Auth snapshot therefore covers only its SQL-managed additions and requires the
existing JPA `organizations` table. It does not invent an incomplete replacement
for that table. Personalize's snapshot comes from literal startup DDL, including
its empty-database views; runtime can rebuild views for external Parquet data.
BigQuery SQL already has business/layer boundaries and stays in Data Warehouse.

The PostgreSQL generator creates disposable databases, replays repository inputs,
exports normalized DDL and verifies restoration, seed defaults and historical
ledger identities. Lab, Chat and Workspace fresh baselines include their old
migration names; deployment against an existing database never runs this baseline.

```sh
python3 scripts/build-sql-snapshots.py --service lms-service
python3 scripts/build-sql-snapshots.py --service lms-service --check
# Run in Personalize's Python environment (duckdb==1.1.3):
python scripts/build-duckdb-schema.py
python scripts/build-duckdb-schema.py --check
python3 scripts/check-sql-releases.py
```

Only use a consolidated file to inspect the schema or deliberately initialize an
empty database. Each service's `schema/README.md` lists the scope and command.
Existing Neon databases need no reapplication. New business changes still require
forward migrations; regenerate the affected snapshot after reviewing the change.

**Fresh-AI exception:** the historical `idx_sr_student_due_today` predicate uses
`CURRENT_DATE`, which PostgreSQL forbids in a partial index. The consolidated
schema uses a valid `next_review_date IS NOT NULL` covering index. This correction
is limited to the fresh baseline and does not change historical SQL or Neon.

## Preserve deployed history

SQL history is organized by service and release. The 2026-11 release groups the
82 existing migration files recorded in this repository as of 2026-11-22.
This is a source-layout change, not a new database migration. No historical SQL statement,
filename, migration ID or existing checksum was changed. No database access is
required to adopt this layout.

```text
<service>/migrations/
  README.md                         # business-oriented index
  releases/
    2026-11/
      manifest.json                 # original filenames and SHA-256
      V001__....sql                  # original immutable migration
      ...
    2026-11.1/                      # example of the next release
      manifest.json
      V026__....sql
```

## Catalogue

| Owner | Index | Application mechanism |
|---|---|---|
| Auth / management | [SQL](../../auth-and-management-service/migrations/README.md) | Operator SQL; existing JPA/runtime behavior retained |
| LMS | [SQL](../../lms-service/migrations/README.md) | Operator SQL and embedded startup guards |
| AI | [SQL](../../ai-service/migrations/README.md) | Operator / deployment SQL, existing task-specific runners |
| Lab | [SQL](../../lab-service/migrations/README.md) | Embedded SQL, `lab_schema_migrations` |
| Chat | [SQL](../../chat-service/migrations/README.md) | Runtime SQL files, `schema_migrations` |
| Farm | [SQL](../../farm-service/migrations/README.md) | Operator SQL; embedded runtime schemas retained |
| DutyLog | [SQL](../../dutylog/backend/migrations/README.md) | Operator SQL; existing startup schema guards retained |
| Workspace | [SQL](../../workspace-service/migrations/README.md) | Startup/CLI, `workspace_migrations`; existing baseline recovery retained |
| Personalize | [SQL](../../personalize-service/migrations/README.md) | DuckDB annotation change, already owned by runtime initialization |

These are not nine interchangeable Neon schemas. Personalize uses DuckDB and
warehouse DDL targets BigQuery. Warehouse SQL already separates `ddl/`,
`transforms/` and `checks/`; those files stay in place. Embedded runtime SQL,
SQL in application code and disposable test fixtures also stay with their code.
This change does not introduce a common migration engine or move table ownership.

## Compatibility

Lab, Chat and Workspace read SQL under release directories and retain the
**basename**, never the relative path, as the historical migration identity.
Execution order is still global filename order, not folder order. Duplicate
basenames are rejected instead of silently skipping a migration. Readiness and
Workspace's manual-schema recovery use the same discovered files as startup.

Explicit CI inputs, flashcard migration discovery, Go embeds, test loaders and
current documentation links point at the new layout. Container copies already
copy the full migration directory, including subdirectories.

Do not rename the existing two LMS `V003` files or AI's `004_graphrag_indexes.sql`
to make numbering look uniform: their current identities and order are historical.
Do not concatenate a released history into a new executable SQL file or mark a
new baseline as applied merely because a database has existing tables.

## Adding a change

1. Put new SQL in the next release directory, with the next unused filename in
   that service's existing version scheme. For an urgent November follow-up,
   `2026-11.1` is sufficient; it need not wait for December.
2. Before first application, related draft DDL can be collected in one migration
   per business change. After application, freeze the file and add a forward
   migration for subsequent changes. Organize the index by business, but execute
   migrations in dependency/version order.
3. Add the filename and its `sha256sum` output to that release's `manifest.json`,
   using the same structure as `2026-11/manifest.json`. Update the service index.
4. Update explicit operator/CI/bootstrap inputs if that service requires them.
   Discovery is not a promise that every service automatically applies all SQL.
5. Regenerate the affected `schema/current.sql` through the appropriate generator.
   Run `python3 scripts/check-sql-releases.py` and the affected service checks.
   Both root CI and the production selection job validate release and snapshot integrity. DutyLog is a submodule: its release metadata is checked when the submodule is available, including after service checkout.

No ledger repair, database reset, Neon command or SQL reapplication is needed
for this organization change. Existing deployed images contain their original
files; updated images contain the same SQL at the new paths.
