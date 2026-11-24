-- The login backups run as (owner: M4 Ziad). Run ONCE per database server, as a superuser:
--   psql "$SUPERUSER_URL" -v ON_ERROR_STOP=1 -v pw='<long random password>' -f ops/backup/create_backup_role.sql
-- (pw is passed raw and quoted here, so any character is safe.) Optional: -v role=<name>, default securefin_backup.
-- Then BACKUP_DATABASE_URL=postgresql://securefin_backup:<password>@<host>:5432/<db>
--
-- Why a separate login: approvals and audit_log FORCE row-level security, so even their owner sees one company
-- at a time and pg_dump as the owner either fails or (with --enable-row-security) silently leaves rows out.
-- BYPASSRLS lets this login read every row; pg_read_all_data (PostgreSQL 14+) gives SELECT on every table and
-- sequence and nothing else. It cannot write, so a leaked backup password cannot change the books.
\if :{?role}
\else
    \set role securefin_backup
\endif
SELECT format('CREATE ROLE %I LOGIN', :'role') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'role') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN BYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'role', :'pw') \gexec
SELECT format('GRANT pg_read_all_data TO %I', :'role') \gexec
-- belt and braces: it has no write grants either
SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'role') \gexec
