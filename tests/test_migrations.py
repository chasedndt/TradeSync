import unittest
from pathlib import Path

from ops.migrate import migration_files, up_sql


ROOT = Path(__file__).resolve().parents[1]

# Numbers reserved by migrations being written on parallel branches
# (2026-09-14: 027, 029, 030 and 031 elsewhere; 028 on this branch;
# 2026-09-15: 031 and 032 elsewhere, 033 on the ops refinements branch). Until the
# branches merge, each sees gaps where the others' numbers belong. A gap at a
# reserved number is allowed; any other gap still fails. The runner applies
# pending versions in order and skips applied ones, so a gap is safe to deploy.
# Empty this set once those branches have merged.
RESERVED_BY_PARALLEL_BRANCHES: set[str] = set()


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

        # Numbered from 001, contiguous apart from reserved numbers, unique,
        # and already in order.
        self.assertEqual(prefixes, sorted(prefixes), "migrations must be ordered")
        self.assertEqual(len(set(prefixes)), len(prefixes), "duplicate prefix")
        self.assertEqual(prefixes[0], "001", "migration numbering must start at 001")
        missing = [
            number
            for number in (f"{i:03d}" for i in range(1, int(prefixes[-1]) + 1))
            if number not in set(prefixes)
        ]
        self.assertEqual(
            [number for number in missing if number not in RESERVED_BY_PARALLEL_BRANCHES],
            [],
            "migration numbering must be contiguous from 001",
        )
        for path in files:
            self.assertTrue(
                up_sql(path.read_text(encoding="utf-8-sig")),
                f"{path.name} has no parseable UP section",
            )


if __name__ == "__main__":
    unittest.main()
