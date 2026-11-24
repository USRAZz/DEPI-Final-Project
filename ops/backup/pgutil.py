"""Shared helpers for the backup and restore-check scripts (plain psycopg, no app code)."""
from __future__ import annotations

import os
import pathlib
import shutil
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

# Tables whose rows must survive a backup. Checked in this order, all must exist.
TABLES = ("companies", "users", "vendors", "bank_accounts", "invoices", "invoice_line_items", "payment_requests",
          "payment_risk", "approval_responses", "approvals", "audit_log")


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


def snapshot(url: str) -> dict:
    """What the database holds right now: alembic revision, rows per table, policy and trigger counts."""
    with psycopg.connect(url) as c:
        rows = {t: c.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))).fetchone()[0]
                for t in TABLES}
        revision = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        policies = c.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'").fetchone()[0]
        triggers = c.execute("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal").fetchone()[0]
        server = c.execute("SHOW server_version").fetchone()[0]
    return {"alembic_revision": revision, "rows": rows, "policies": policies, "triggers": triggers,
            "server_version": server}
