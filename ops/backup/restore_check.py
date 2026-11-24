"""Prove a backup can be restored (owner: M4 Ziad). Run it monthly and after any change to the schema.

    python ops/backup/restore_check.py --url "$RESTORE_ADMIN_URL" --backup-dir backups

Takes the newest backups/securefin-*.dump (or --dump FILE), checks its sha256 against the manifest, restores it
into a scratch database (default securefin_restore_check, dropped first), then checks:

  1. alembic revision equals the manifest's
  2. row count of every table equals the manifest's
  3. row-level security policies and triggers came back (same counts as the manifest)
  4. every company's audit_log hash chain verifies, read through the gateway's own code as role securefin_gateway
     (so the grants and RLS policies are proven to work, not only to exist)
  5. the append-only trigger still refuses an UPDATE on audit_log

--url is a superuser of a server you can throw away (local Docker postgres or CI): it creates the scratch
database and, if missing, the NOLOGIN roles securefin_app/securefin_gateway that the dump's grants and policies
name (roles are per server and not in a dump). It never touches the database the backup came from.
Exit code 0 = restore proven.
--keep-db leaves the scratch database for inspection.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import psycopg
from psycopg import sql

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import pgutil  # noqa: E402
from backup import sha256  # noqa: E402

APP_ROLES = ("securefin_app", "securefin_gateway")


def gateway_audit_log():
    """services/gateway/app loaded as package securefin_gateway (every service is a package named app)."""
    root = REPO / "services" / "gateway" / "app"
    spec = importlib.util.spec_from_file_location("securefin_gateway", root / "__init__.py",
                                                  submodule_search_locations=[str(root)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["securefin_gateway"] = pkg
    spec.loader.exec_module(pkg)
    return importlib.import_module("securefin_gateway.audit_log")


def newest_dump(backup_dir: pathlib.Path) -> pathlib.Path:
    dumps = sorted(d for d in backup_dir.glob("securefin-*.dump") if d.with_suffix(".json").exists())
    if not dumps:
        raise SystemExit(f"no securefin-*.dump with its .json manifest in {backup_dir}")
    return dumps[-1]


def restore(dump: pathlib.Path, admin_url: str, scratch: str) -> str:
    with psycopg.connect(admin_url, autocommit=True) as c:
        c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(scratch)))
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(scratch)))
        # Roles live in the server, not in the dump: a fresh server needs them before the GRANTs and policies
        # that name them can be restored (same NOLOGIN roles as migration 0001).
        for role in APP_ROLES:
            c.execute(sql.SQL("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {r}) THEN "
                              "CREATE ROLE {i} NOLOGIN; END IF; END $$").format(r=sql.Literal(role), i=sql.Identifier(role)))
            c.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(role)))
    url = pgutil.with_database(admin_url, scratch)
    bare_url, env = pgutil.split_password(url)  # password via PGPASSWORD, never on the command line
    # --no-owner: the restoring login owns the copy; grants to securefin_app/securefin_gateway are kept
    result = subprocess.run([pgutil.tool("pg_restore"), "--no-owner", "--exit-on-error", "--no-password",
                             f"--dbname={bare_url}", str(dump)], capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise SystemExit("pg_restore failed:\n" + result.stderr.strip())
    return url


def check(url: str, manifest: dict) -> list[str]:
    """Problems found; empty means the restore is proven."""
    problems = []
    now = pgutil.snapshot(url)
    if now["alembic_revision"] != manifest["alembic_revision"]:
        problems.append(f"alembic revision {now['alembic_revision']} != {manifest['alembic_revision']}")
    for table, count in manifest["rows"].items():
        if now["rows"].get(table) != count:
            problems.append(f"{table}: {now['rows'].get(table)} rows, backup had {count}")
    for key in ("policies", "triggers"):
        if now[key] != manifest[key]:
            problems.append(f"{key}: {now[key]} after restore, {manifest[key]} before")

    from sqlalchemy import create_engine
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        log = gateway_audit_log().PostgresAuditLog(engine)
        with psycopg.connect(url) as c:
            companies = [r[0] for r in c.execute("SELECT DISTINCT company_id FROM audit_log ORDER BY 1")]
        for company in companies:
            seen = len(log.entries(company))
            broken = log.verify(company)
            if broken is not None:
                problems.append(f"audit_log chain of company {company} breaks at entry {broken}")
            elif seen == 0:
                problems.append(f"company {company}: securefin_gateway reads no audit rows (grants or RLS lost)")
    finally:
        engine.dispose()

    if companies:  # tamper attempts, always rolled back; app.company_id set so forced RLS shows the row
        for statement in ("UPDATE audit_log SET result = 'tampered'", "DELETE FROM audit_log", "TRUNCATE audit_log"):
            with psycopg.connect(url) as c:
                c.execute("SELECT set_config('app.company_id', %s, true)", (str(companies[0]),))
                try:
                    c.execute(statement)
                    problems.append(f"append-only trigger did not refuse: {statement}")
                except psycopg.Error:
                    pass  # refused, as it must be
                c.rollback()
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("RESTORE_ADMIN_URL"))
    ap.add_argument("--backup-dir", default="backups")
    ap.add_argument("--dump", help="a specific .dump file instead of the newest")
    ap.add_argument("--scratch-db", default="securefin_restore_check")
    ap.add_argument("--keep-db", action="store_true")
    args = ap.parse_args(argv)
    if not args.url:
        print("set --url or RESTORE_ADMIN_URL", file=sys.stderr)
        return 2
    admin = pgutil.libpq_url(args.url)
    dump = pathlib.Path(args.dump) if args.dump else newest_dump(pathlib.Path(args.backup_dir))
    manifest = json.loads(dump.with_suffix(".json").read_text(encoding="utf-8"))
    if sha256(dump) != manifest["sha256"]:
        print(f"{dump.name}: sha256 does not match its manifest (file damaged or replaced)", file=sys.stderr)
        return 4

    url = restore(dump, admin, args.scratch_db)
    try:
        problems = check(url, manifest)
    finally:
        if not args.keep_db:
            with psycopg.connect(admin, autocommit=True) as c:
                c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(args.scratch_db)))
    if problems:
        print(f"RESTORE CHECK FAILED for {dump.name}:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1
    print(f"restore proven: {dump.name} -> {sum(manifest['rows'].values())} rows, revision "
          f"{manifest['alembic_revision']}, audit chains intact, append-only trigger active")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
