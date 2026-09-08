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
        """Assert the invariants, not a fixed list.

        A hard-coded roster fails every time a migration is added, which says
        nothing about whether the migrations are well formed.
        """
        files = migration_files(ROOT / "ops/migrations")
        self.assertTrue(files, "no migrations found")
        prefixes = [path.name[:3] for path in files]

        # Numbered from 001, contiguous, unique, and already in order.
        self.assertEqual(prefixes, sorted(prefixes), "migrations must be ordered")
        self.assertEqual(len(set(prefixes)), len(prefixes), "duplicate prefix")
        self.assertEqual(
            prefixes,
            [f"{i:03d}" for i in range(1, len(prefixes) + 1)],
            "migration numbering must be contiguous from 001",
        )
        for path in files:
            self.assertTrue(
                up_sql(path.read_text(encoding="utf-8-sig")),
                f"{path.name} has no parseable UP section",
            )


if __name__ == "__main__":
    unittest.main()
