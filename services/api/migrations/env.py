"""Alembic environment. Run from services/api with DATABASE_URL set:

    alembic upgrade head

target_metadata (the api's ORM tables) is only needed for `alembic revision --autogenerate`. It is loaded from
app/db.py by file path, so other services (the gateway's tests) can run these migrations even though their own
package is also called `app`.
"""
import importlib.util
import os
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool


def _api_db():
    spec = importlib.util.spec_from_file_location("securefin_api_db", Path(__file__).resolve().parents[1] / "app" / "db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_db = _api_db()
target_metadata = _db.Base.metadata


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return _db.normalize_url(url)


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = engine_from_config({"sqlalchemy.url": _url()}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
