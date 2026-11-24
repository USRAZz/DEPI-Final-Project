-- The login backups run as (owner: M4 Ziad). Run ONCE per database server, as a superuser:
--   psql "$SUPERUSER_URL" -v pw="'<a long random password>'" -f ops/backup/create_backup_role.sql
-- Then BACKUP_DATABASE_URL=postgresql://securefin_backup:<password>@<host>:5432/<db>
--
-- Why a separate login: approvals and audit_log FORCE row-level security, so even their owner sees one company
-- at a time and pg_dump as the owner either fails or (with --enable-row-security) silently leaves rows out.
-- BYPASSRLS lets this login read every row; pg_read_all_data (PostgreSQL 14+) gives SELECT on every table and
-- sequence and nothing else. It cannot write, so a leaked backup password cannot change the books.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'securefin_backup') THEN
        CREATE ROLE securefin_backup LOGIN BYPASSRLS;
    END IF;
END $$;
ALTER ROLE securefin_backup WITH LOGIN BYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :pw;
GRANT pg_read_all_data TO securefin_backup;
ALTER ROLE securefin_backup SET default_transaction_read_only = on;  -- belt and braces: it has no write grants either
