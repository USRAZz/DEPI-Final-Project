"""Shared helpers for the backup and restore-check scripts (plain psycopg, no app code)."""
from __future__ import annotations

import os
import pathlib
import shutil
from urllib.parse import unquote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

# Tables whose rows must survive a backup. Checked in this order, all must exist.
TABLES = ("companies", "users", "vendors", "bank_accounts", "invoices", "invoice_line_items", "payment_requests",
          "payment_risk", "approval_responses", "approvals", "audit_log")


def split_password(url: str) -> tuple[str, dict]:
    """(URL without the password, env with PGPASSWORD) so the password never shows in `ps` output."""
    parts = urlsplit(url)
    if parts.password is None:
        return url, dict(os.environ)
    netloc = parts.netloc.rsplit("@", 1)
    user = netloc[0].split(":", 1)[0]
    bare = urlunsplit((parts.scheme, f"{user}@{netloc[1]}", parts.path, parts.query, parts.fragment))
    return bare, {**os.environ, "PGPASSWORD": unquote(parts.password)}


def libpq_url(url: str) -> str:
    """postgresql+psycopg://... (SQLAlchemy) -> postgresql://... (libpq, pg_dump)."""
    parts = urlsplit(url)
    scheme = "postgresql" if parts.scheme.startswith(("postgresql", "postgres")) else parts.scheme
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + database, parts.query, parts.fragment))


def tool(name: str) -> str:
    folder = os.environ.get("PG_BIN")
    path = str(pathlib.Path(folder) / name) if folder else shutil.which(name)
    if not path:
        raise SystemExit(f"{name} not found: install the PostgreSQL client tools or set PG_BIN")
    return path


def check_backup_login(url: str) -> str | None:
    """None when this login sees every row (superuser or BYPASSRLS); otherwise why it does not."""
    with psycopg.connect(url) as c:
        row = c.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()
    if row and (row[0] or row[1]):
        return None
    return ("this login does not bypass row-level security, so approvals and audit_log would be missing from the "
            "backup. Use a superuser or a role created WITH BYPASSRLS (see ops/README.md).")


def snapshot(url: str = "", conn=None) -> dict:
    """What the database holds: alembic revision, rows per table, policy and trigger counts.

    Pass `conn` to count inside an open transaction (backup.py counts in the snapshot pg_dump then uses)."""
    if conn is not None:
        return _counts(conn)
    with psycopg.connect(url) as c:
        return _counts(c)


def _counts(c) -> dict:
    rows = {t: c.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))).fetchone()[0] for t in TABLES}
    revision = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    policies = c.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'").fetchone()[0]
    triggers = c.execute("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal").fetchone()[0]
    server = c.execute("SHOW server_version").fetchone()[0]
    return {"alembic_revision": revision, "rows": rows, "policies": policies, "triggers": triggers,
            "server_version": server}
