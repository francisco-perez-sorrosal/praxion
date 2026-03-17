# Database Migration Strategies

Patterns for evolving database schemas safely in production, with emphasis on zero-downtime deployments and rollback capability.

## Expand-Contract Pattern

The primary strategy for making breaking schema changes without downtime. Splits a dangerous migration into safe, incremental steps.

### Phase 1: Expand

Add the new structure alongside the old. Both old and new application versions continue to work.

```sql
-- Example: Rename column 'name' to 'full_name'
-- Step 1: Add new column
ALTER TABLE users ADD COLUMN full_name VARCHAR(255);
```

- Deploy this migration independently, before any code changes
- The new column is nullable or has a default value
- No existing queries break

### Phase 2: Migrate

Update application code to write to both structures. Backfill existing data.

```sql
-- Step 2: Backfill data
UPDATE users SET full_name = name WHERE full_name IS NULL;
```

- Deploy application code that writes to both `name` and `full_name`
- All new writes populate both columns
- Backfill script runs for existing rows
- Verify data consistency between old and new columns

### Phase 3: Contract

Remove the old structure after all consumers have migrated.

```sql
-- Step 3: Drop old column (only after all readers use full_name)
ALTER TABLE users DROP COLUMN name;
```

- Confirm zero reads from the old column (query logs, application audit)
- Deploy the drop migration
- Keep the ability to re-add if needed (backfill from the new column)

### Expand-Contract Timeline

```text
T0: Deploy expand migration (add new column)
T1: Deploy dual-write code + start backfill
T2: Verify data consistency
T3: Migrate all readers to new column
T4: Deploy contract migration (drop old column)
```

Minimum recommended gap between T0 and T4: one full deployment cycle. For critical systems, allow 2-4 weeks.

## Zero-Downtime Migration Checklist

Apply these rules to every production migration:

- [ ] Migration is backward-compatible with the currently deployed application code
- [ ] No `ALTER TABLE` acquires an exclusive lock on a large table (use online DDL tools for MySQL, `CREATE INDEX CONCURRENTLY` for PostgreSQL)
- [ ] No `NOT NULL` constraint added without a default value on an existing column
- [ ] No column renames or drops without the expand-contract pattern
- [ ] Data backfill runs in batches, not as a single transaction
- [ ] Migration tested against a production-sized dataset to verify execution time
- [ ] Rollback migration exists and has been tested
- [ ] Application code handles both pre-migration and post-migration schemas during deployment

## Forward-Only Migrations

Treat migrations as an append-only sequence. Each migration has a unique, monotonically increasing identifier (timestamp or sequence number).

### Principles

- Never edit a migration that has been applied to any shared environment
- Fix mistakes with a new corrective migration, not by modifying the original
- Store migrations in version control alongside application code
- Migration filenames: `YYYYMMDD_HHMMSS_description.sql` or framework equivalent

### Migration File Structure

```text
migrations/
  20250115_120000_create_users.sql
  20250120_093000_add_email_index.sql
  20250203_141500_add_full_name_to_users.sql
  20250210_100000_drop_name_from_users.sql
```

## Migration Testing

### Test Against Production-Like Data

A migration that completes in milliseconds on 100 rows may take hours on 10 million rows. Test with:

- Production-sized tables (anonymized production snapshot or generated data matching cardinality)
- Realistic index state
- Concurrent read/write load (to catch lock contention)

### Test the Rollback

- Run the forward migration, then the rollback, then the forward migration again
- Verify data integrity after each step
- Confirm the application works correctly after rollback

## Rollback Strategies

### Reversible Migrations

Write explicit down/rollback migrations for every up migration:

```sql
-- Up: add column
ALTER TABLE orders ADD COLUMN tracking_number VARCHAR(100);

-- Down: remove column
ALTER TABLE orders DROP COLUMN tracking_number;
```

### Non-Reversible Migrations

Some migrations cannot be cleanly reversed (data type narrowing, column merges). For these:

1. Document that the migration is non-reversible in the migration file
2. Take a logical backup (table dump) before applying
3. Provide a restoration script that recreates the pre-migration state from the backup
4. Test the restoration script before applying the forward migration

### Rollback Decision Framework

| Situation | Action |
| --- | --- |
| Migration failed mid-execution | Roll back the transaction (if transactional DDL is supported) |
| Migration succeeded but app has bugs | Deploy fix-forward code; avoid schema rollback if possible |
| Migration caused data corruption | Restore from backup; investigate root cause before retrying |
| Migration is too slow | Cancel, analyze, add indexes or batch processing, retry |

## Data Backfill Patterns

### Batched Backfill

Process rows in batches to avoid long-running transactions and lock contention:

```sql
-- Process 1000 rows at a time
UPDATE users
SET full_name = name
WHERE full_name IS NULL
  AND id > :last_processed_id
ORDER BY id
LIMIT 1000;
```

- Track progress with a cursor (last processed ID)
- Add a small delay between batches to reduce database load
- Log progress for monitoring and resumability
- Make backfills idempotent -- safe to re-run if interrupted

### Online Backfill with Dual-Write

For tables under active write load:

1. Deploy dual-write code (writes to both old and new columns)
2. Run batched backfill for existing rows
3. Verify consistency: all rows have the new column populated
4. Handle edge cases: rows written between backfill batches are covered by dual-write

## Tooling Patterns

Migration tools vary by language and framework, but share common capabilities:

| Capability | What to Look For |
| --- | --- |
| **Version tracking** | Schema version table recording applied migrations |
| **Transactional DDL** | Wrap migration in a transaction (PostgreSQL supports this; MySQL does not for DDL) |
| **Dry-run mode** | Preview SQL without executing |
| **Locking awareness** | Detect or avoid long-held locks on large tables |
| **Rollback generation** | Automatic or manual down-migration scaffolding |
| **CI integration** | Run pending migrations in test environments before production |

Common tools by ecosystem: Alembic/SQLAlchemy (Python), Flyway/Liquibase (Java/JVM), Prisma Migrate (Node.js), Goose/Atlas (Go), Diesel (Rust), ActiveRecord migrations (Ruby).
