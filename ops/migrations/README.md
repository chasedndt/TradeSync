# TradeSync Database Migrations

This directory contains SQL migration files for managing schema changes in the TradeSync database.

## Migration File Naming Convention

Migration files follow this naming pattern:
```
<version>_<description>.sql
```

Examples:
- `001_initial_schema.sql`
- `002_add_agent_performance_table.sql`
- `003_add_index_to_events.sql`

**Version numbers** should be sequential integers padded with zeros (001, 002, 003, etc.).

## Migration File Structure

Each migration file contains two sections:

```sql
-- UP
-- SQL statements to apply the migration
CREATE TABLE ...;

-- DOWN
-- SQL statements to rollback the migration
DROP TABLE ...;
```

- **UP section**: Contains SQL to apply the migration (creating tables, adding columns, etc.)
- **DOWN section**: Contains SQL to rollback the migration (should reverse the UP changes)

## Creating a New Migration

Use the migration tool to generate a new migration file:

```bash
python ops/migrate.py create <description>
```

This will create a new file with:
- Auto-incremented version number
- Timestamp-based unique identifier
- Template with UP and DOWN sections

Example:
```bash
python ops/migrate.py create add_user_preferences_table
```

## Running Migrations

### Apply all pending migrations:
```bash
python ops/migrate.py up
```

### Rollback the last migration:
```bash
python ops/migrate.py down
```

### Check migration status:
```bash
python ops/migrate.py status
```

## Migration Tracking

The migration tool automatically creates a `schema_migrations` table in your database to track which migrations have been applied:

```sql
CREATE TABLE schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  description TEXT NOT NULL
);
```

## Best Practices

1. **Always test migrations**: Test both UP and DOWN sections before committing
2. **Keep migrations small**: One logical change per migration file
3. **Make migrations reversible**: Always provide a proper DOWN section
4. **Use transactions**: Migrations are executed in transactions and rollback on failure
5. **Don't modify existing migrations**: Once applied to production, create a new migration instead

## Initial Setup

For a fresh database, run:
```bash
python ops/migrate.py up
```

This will apply all migrations starting from `001_initial_schema.sql`.
