# Operations (owner: M4 Ziad)

## Backups and restore

### What is backed up

Everything in the SecureFin database: schema, data, grants, row-level security policies and triggers, as one
`pg_dump` custom-format file. Next to each dump is a manifest (`.json`) with the Alembic revision, the row count of
every table and the dump's sha256, so a restore can be *proven* rather than assumed.

| File | Job |
|------|-----|
| `backup/create_backup_role.sql` | creates the read-only `securefin_backup` login (run once per server) |
| `backup/backup.py` | takes a backup, writes the manifest, keeps the newest `--keep` (default 14) |
| `backup/restore_check.py` | restores the newest backup into a scratch database and checks it (below) |
| `backup/Dockerfile`, `compose.yaml` | the `backup` container: one backup now, then every 24 h |
| `../tests/test_backup_restore.py` | the drill, run by `.github/workflows/backup-drill.yml` |

### Why backups need their own login

`approvals` and `audit_log` **force** row-level security, so even the table owner only sees one company at a
time. `pg_dump` as the owner therefore stops with `query would be affected by row-level security policy for
table "approvals"`, and with `--enable-row-security` it finishes but leaves those rows out without a warning.
The backup login has `BYPASSRLS` + `pg_read_all_data` and no write rights. `backup.py` checks this first and
refuses (exit 3) a login that would produce an incomplete backup.

### Set up (once)

```bash
# local / Docker Postgres: as the superuser
psql "postgresql://securefin:securefin@localhost:5432/securefin" -v pw="'<long random password>'" \
     -f ops/backup/create_backup_role.sql
# .env
BACKUP_DATABASE_URL=postgresql://securefin_backup:<password>@postgres:5432/securefin
```

**Neon:** roles made in the Neon console get `BYPASSRLS` through `neon_superuser`, so either run the script
as the project owner or create a dedicated role in the console. Use the **direct** host (no `-pooler`):
`pg_dump` uses session `SET`s that the pooler does not support. Neon also keeps point-in-time history of its own;
these dumps are the copy that is independent of Neon.

### Take a backup

```bash
docker compose --profile ops up -d backup        # runs now, then every BACKUP_INTERVAL_HOURS
docker compose --profile ops logs backup         # "backup written: /backups/securefin-...dump (… rows …)"
# or by hand (pg_dump 16+ on PATH):
python ops/backup/backup.py --url "$BACKUP_DATABASE_URL" --out-dir backups
```

The dumps hold invoices, IBANs and the audit log: keep them off public storage, copy them off the machine
(another disk, or a private bucket), and never commit `backups/`.

### Prove a restore (monthly, and after every schema change)

```bash
python ops/backup/restore_check.py --url "postgresql://postgres:<pw>@localhost:5432/postgres" --backup-dir backups
```

It never touches the source database. It restores into `securefin_restore_check` and fails unless:

1. the sha256 matches the manifest (exit 4 if the file was damaged or replaced),
2. the Alembic revision and the row count of every table match,
3. the RLS policies and triggers came back,
4. every company's audit chain verifies when read **through the gateway's own code as `securefin_gateway`**,
5. `UPDATE`, `DELETE` and `TRUNCATE` on `audit_log` are still refused.

CI runs the same drill on a throwaway Postgres when `ops/backup/`, the migrations or the test change, on the 1st of
every month, and by hand from Actions → *Backup drill* → Run workflow. Record each monthly manual drill on real
data below.

### Restore for real (incident)

1. Stop writers: `docker compose stop api gateway agent`.
2. Run `restore_check.py` on the dump you mean to use. Do not restore a dump that fails it.
3. Restore into a **new** database, never over the damaged one:
   `createdb securefin_restored && pg_restore --no-owner --exit-on-error -d securefin_restored <file>.dump`
4. Point `DATABASE_URL` at it, start the services, and check every company's chain:
   `curl -X POST localhost:8002/v1/audit/verify -H "Content-Type: application/json" -H "X-Service-Token: $AUDIT_VERIFY_TOKEN" -d '{"company_id": 1}'`
   (expect `"ok": true`).
5. Keep the damaged database until the incident is written up.

| Date | Dump | Who | Result |
|------|------|-----|--------|
| | | | |
