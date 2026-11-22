import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("sql_snapshots", Path(__file__).parents[1] / "build-sql-snapshots.py")
snapshots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshots)


class SQLSnapshotTests(unittest.TestCase):
    def test_compaction_preserves_sql_literals_and_function_bodies(self):
        source = '''-- Dump header
\\restrict random
SET transaction_timeout = 0;
CREATE FUNCTION f() RETURNS text AS $body$
-- A comment inside a function is source, not a dump header.
BEGIN RETURN 'line one
-- literal line two'; END;
$body$ LANGUAGE plpgsql;
INSERT INTO t VALUES ('one
-- two'), ('it''s three');
\\unrestrict random
'''
        result = snapshots.compact_dump(source)
        self.assertNotIn("Dump header", result)
        self.assertNotIn("\\restrict random", result)
        self.assertNotIn("SET transaction_timeout", result)
        self.assertIn("-- A comment inside a function", result)
        self.assertIn("-- literal line two", result)
        self.assertIn("-- two", result)
        self.assertIn("it''s three", result)

    def test_baseline_ledger_uses_original_names_not_paths(self):
        sql = snapshots.ledger_sql("workspace-service", [Path("releases/example/001_workspace.sql")])
        self.assertIn("('001_workspace.sql')", sql)
        self.assertNotIn("releases/example", sql)
        self.assertIn("DEFAULT now()", sql)


if __name__ == "__main__":
    unittest.main()
