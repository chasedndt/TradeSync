"""Small transactional migration runner for TradeSync PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

MIGRATION_TABLE_SQL = """
create table if not exists schema_migrations (
  version text primary key,
  description text not null,
  applied_at timestamptz not null default now()
)
"""


def up_sql(contents: str) -> str:
    marker = "-- DOWN"
    if marker not in contents:
        raise ValueError("migration is missing a -- DOWN boundary")
    before, _ = contents.split(marker, 1)
    return before.removeprefix("-- UP").strip()


def migration_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.glob("[0-9][0-9][0-9]_*.sql")
        if path.is_file()
    )


async def apply_pending_migrations(conn, directory: Path) -> list[str]:
    await conn.execute(MIGRATION_TABLE_SQL)
    rows = await conn.fetch("select version from schema_migrations")
    applied = {str(row["version"]) for row in rows}
    newly_applied: list[str] = []
    for path in migration_files(directory):
        version, _, description = path.stem.partition("_")
        if version in applied:
            continue
        sql = up_sql(path.read_text(encoding="utf-8-sig"))
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "insert into schema_migrations(version, description) values($1,$2)",
                version,
                description,
            )
        newly_applied.append(version)
    return newly_applied


def dsn_from_env() -> str:
    explicit = os.getenv("PG_DSN")
    if explicit:
        return explicit
    user = os.getenv("POSTGRES_USER", "tradesync")
    password = os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("POSTGRES_DB", "tradesync")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def run(command: str) -> int:
    import asyncpg

    directory = Path(__file__).parent / "migrations"
    conn = await asyncpg.connect(dsn_from_env())
    try:
        await conn.execute(MIGRATION_TABLE_SQL)
        if command == "status":
            rows = await conn.fetch(
                "select version, description, applied_at from schema_migrations order by version"
            )
            for row in rows:
                print(f"{row['version']} applied {row['description']} {row['applied_at']}")
            known = {str(row["version"]) for row in rows}
            for path in migration_files(directory):
                version, _, description = path.stem.partition("_")
                if version not in known:
                    print(f"{version} pending {description}")
            return 0
        applied = await apply_pending_migrations(conn, directory)
        print("Applied migrations: " + (", ".join(applied) if applied else "none"))
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply or inspect TradeSync migrations")
    parser.add_argument("command", choices=("up", "status"), default="up", nargs="?")
    args = parser.parse_args()
    return asyncio.run(run(args.command))


if __name__ == "__main__":
    raise SystemExit(main())
