# Disaster Recovery, Backup & Restore Runbook

This runbook documents the data protection architecture, backup protocols, disaster recovery procedures, and dual-store reconciliation routines.

---

## 1. Storage Topology & Authoritative Source Rules

- **Production Authority**: PostgreSQL on Supabase (`SUPABASE_URL` + `SUPABASE_SECRET_KEY`).
  - All write operations (account allocations, key rotations, replacement events) commit directly to Supabase.
  - **F04 Invariant**: When Supabase is configured and returns an error, the operation MUST return `OperationResult.failure()`. Local SQLite fallback for transactional writes is strictly prohibited to prevent data divergence.
- **Local Runtime / SQLite**:
  - Used for development, CI hermetic test suites, and read caching.
  - File path: `accounts.db` (WAL mode enabled).

---

## 2. Backup Procedures

### A. Production PostgreSQL (Supabase)
1. **Automated Backups**: Daily automated snapshots managed via Supabase Platform (retained 7–30 days depending on tier).
2. **Manual On-Demand Logical Export**:
   Run prior to major migrations, schema changes, or bulk imports:
   ```bash
   pg_dump "postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres" \
     --format=custom \
     --file="backup_$(date +%Y%m%d_%H%M%S).dump"
   ```
3. **Table-Specific Cold Backup (SQL)**:
   ```sql
   -- Create instant shadow tables before executing mass updates
   CREATE TABLE netflix_accounts_snapshot_20261005 AS SELECT * FROM netflix_accounts;
   CREATE TABLE access_keys_snapshot_20261005 AS SELECT * FROM access_keys;
   CREATE TABLE replacement_events_snapshot_20261005 AS SELECT * FROM replacement_events;
   ```

### B. Local SQLite Database
Run an atomic hot backup while the server is running without risking database locking:
```python
import sqlite3
import datetime

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
conn = sqlite3.connect("accounts.db")
conn.execute(f"VACUUM INTO 'accounts_backup_{timestamp}.db'")
conn.close()
print(f"Snapshot created: accounts_backup_{timestamp}.db")
```

---

## 3. Disaster Recovery & Restore Procedures

### Scenario 1: Point-in-Time Schema Recovery on Supabase
1. **Isolate Traffic**: Temporarily set application to maintenance mode or stop worker containers to prevent new writes.
2. **Restore Logical Dump**:
   ```bash
   pg_restore --clean --if-exists --no-owner --no-privileges \
     -d "postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres" \
     backup_20261005_120000.dump
   ```
3. **Verify Integrity**:
   Execute integrity checks:
   ```sql
   -- 1. Verify no orphan access keys
   SELECT code, assigned_email FROM access_keys 
   WHERE assigned_email NOT IN (SELECT email FROM netflix_accounts);

   -- 2. Verify capacity bounds
   SELECT assigned_email, COUNT(*) as code_count 
   FROM access_keys 
   GROUP BY assigned_email 
   HAVING COUNT(*) > 4;
   ```
4. **Resume Traffic**: Unfreeze server processes.

### Scenario 2: Rollback of Problematic Allocation / Replacement
1. Inspect `replacement_events` audit table:
   ```sql
   SELECT id, request_id, code, previous_account, replacement_account, created_at 
   FROM replacement_events 
   ORDER BY created_at DESC LIMIT 10;
   ```
2. Revert link for specific access code:
   ```sql
   UPDATE access_keys 
   SET assigned_email = 'previous_account@netflix.com', 
       assignment_version = assignment_version + 1
   WHERE code = 'TARGET_CODE';
   ```

---

## 4. Reconciliation Checklist

Run reconciliation to verify data consistency:
- Total active keys with valid expiration dates: $\ge 0$.
- Orphan keys count: exactly $0$.
- Shared accounts exceeding capacity: exactly $0$.
- Outbox pending notifications: successfully dispatched or retryable.
