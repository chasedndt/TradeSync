import unittest
from pathlib import Path

from ops.migrate import migration_files, up_sql


ROOT = Path(__file__).resolve().parents[1]


class MigrationRunnerTests(unittest.TestCase):
    def test_up_parser_never_includes_down_statements(self):
        sql = up_sql("-- UP\ncreate table safe(id int);\n-- DOWN\ndrop table safe;")
        self.assertIn("create table safe", sql)
        self.assertNotIn("drop table", sql)

    def test_all_repository_migrations_have_parseable_up_sections(self):
        files = migration_files(ROOT / "ops/migrations")
        self.assertEqual([path.name[:3] for path in files], ["001", "002", "003"])
        for path in files:
            self.assertTrue(up_sql(path.read_text(encoding="utf-8-sig")))


if __name__ == "__main__":
    unittest.main()
