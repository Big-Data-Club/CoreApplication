# Consolidated Personalize schema

[`current.sql`](current.sql) combines the final DuckDB tables, columns, indexes
and views from `LakehouseService._init_tables` and its empty-database view profile.
For example, `notebook_entries.annotation` is included directly in CREATE TABLE,
instead of requiring the reader to find a separate ALTER statement.

This is DuckDB SQL, not Neon/PostgreSQL SQL. Runtime remains the owner of schema
initialization and may refresh views when external Parquet files are available.
The snapshot was generated and restored entirely in memory; no production DuckDB
file or learner record was opened.

From the repository root, in a Python environment with the existing Personalize
dependency `duckdb==1.1.3`:

```sh
python scripts/build-duckdb-schema.py
python scripts/build-duckdb-schema.py --check
python3 scripts/check-sql-releases.py
```

The generator extracts literal DDL using Python AST; it does not import or start
the application. Input and output hashes are recorded in `manifest.json`.
Historical [SQL](../migrations/README.md) remains immutable. Runtime and snapshot
changes belong in the same reviewed release.
