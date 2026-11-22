#!/usr/bin/env python3
"""Consolidate Personalize's literal startup DDL in memory, without application IO."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "personalize-service"
SOURCE = SERVICE / "app/services/lakehouse.py"


def startup_ddl():
    tree = ast.parse(SOURCE.read_text())
    statements = []
    for method in ("_init_tables", "refresh_views"):
        function = next(node for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef) and node.name == method)
        for node in sorted(ast.walk(function), key=lambda item: getattr(item, "lineno", 0)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "execute" or not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            sql = node.args[0].value
            if isinstance(sql, str) and sql.strip().upper().startswith(("CREATE", "ALTER")):
                statements.append(sql)
    return statements


def dump(connection):
    tables = [row[0] for row in connection.execute(
        "SELECT sql FROM duckdb_tables() WHERE NOT internal AND schema_name='main' ORDER BY table_name").fetchall()]
    indexes = [row[0] for row in connection.execute(
        "SELECT sql FROM duckdb_indexes() WHERE schema_name='main' ORDER BY table_name,index_name").fetchall()]
    # Preserve creation order, because later views depend on earlier views.
    views = [row[0] for row in connection.execute(
        "SELECT sql FROM duckdb_views() WHERE NOT internal AND schema_name='main' ORDER BY view_oid").fetchall()]
    return "\n\n".join(tables + indexes + views) + "\n"


def main():
    import duckdb
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with duckdb.connect(":memory:") as original, duckdb.connect(":memory:") as restored:
        for statement in startup_ddl():
            original.execute(statement)
        sql = dump(original)
        restored.execute(sql)
        if dump(restored) != sql:
            raise RuntimeError("Consolidated DuckDB DDL differs after restoration")
        output = ("-- Consolidated DuckDB startup schema, including final notebook annotation column.\n"
                  "-- Empty-database view profile; runtime refreshes external Parquet views.\n"
                  "-- Reconstructed in memory; no production data was accessed.\n\n" + sql)
        directory = SERVICE / "schema"
        if args.check:
            with duckdb.connect(":memory:") as checked:
                checked.execute((directory / "current.sql").read_text())
                if dump(checked) != sql:
                    raise RuntimeError("Personalize consolidated schema is out of date")
        else:
            directory.mkdir(exist_ok=True)
            sources = [SOURCE, *sorted((SERVICE / "migrations").rglob("*.sql"))]
            (directory / "current.sql").write_text(output)
            (directory / "manifest.json").write_text(json.dumps({
                "engine": f"DuckDB {duckdb.__version__}", "source": "literal startup DDL, no Parquet",
                "inputs": [{"path": str(path.relative_to(SERVICE)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sources],
                "current_sha256": hashlib.sha256(output.encode()).hexdigest(),
            }, indent=2) + "\n")
    print("Personalize: consolidated and restored DuckDB tables, indexes and views in memory.")


if __name__ == "__main__":
    main()
