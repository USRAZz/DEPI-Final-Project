"""Database access for the gateway's own tables (approvals, audit_log; GitHub issue #15).

Every transaction runs as role securefin_gateway with app.company_id set, so row-level security applies and
the gateway can only SELECT/INSERT these two tables (see services/api/migrations/versions/0001). The session
time zone is UTC so timestamps read back exactly as they were signed and hashed.
"""
import os
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text


def build_engine() -> Engine | None:
    """None when DATABASE_URL is not set (local runs and unit tests use the in-memory stores)."""
    url = os.environ.get("DATABASE_URL")
    return create_engine(url, pool_pre_ping=True) if url else None


@contextmanager
def tenant_tx(engine: Engine, company_id: int):
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE securefin_gateway"))
        conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        conn.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": str(company_id)})
        yield conn
