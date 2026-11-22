import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("sql_releases", Path(__file__).parents[1] / "check-sql-releases.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class SQLReleaseTests(unittest.TestCase):
    def test_released_sql_cannot_be_changed_or_shadowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "releases/2026-11"
            directory.mkdir(parents=True)
            sql = directory / "V001.sql"
            original = b"SELECT 1;\n"
            sql.write_bytes(original)
            (directory / "manifest.json").write_text(json.dumps({"release": "2026-11", "files": [{"name": sql.name, "sha256": hashlib.sha256(original).hexdigest()}]}))
            self.assertEqual(release.validate_service(root), 1)
            sql.write_text("SELECT 2;")
            with self.assertRaisesRegex(ValueError, "Released SQL changed"):
                release.validate_service(root)
            sql.write_bytes(original)
            (root / "V001.sql").write_bytes(original)
            with self.assertRaisesRegex(ValueError, "Duplicate migration name|missing from release manifest"):
                release.validate_service(root)

    def test_all_services_have_valid_released_sql(self):
        for service in release.SERVICES:
            with self.subTest(service=service):
                self.assertGreater(release.validate_service(release.ROOT / service / "migrations"), 0)


if __name__ == "__main__":
    unittest.main()
