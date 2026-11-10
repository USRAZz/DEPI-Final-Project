import os

from fastapi import FastAPI

from .gateway import Gateway, build_gateway
from .risk_features import internal_router
from .routes import router
from .store import DataStore, seeded_store


def default_store() -> DataStore:
    """PostgreSQL when DATABASE_URL is set (run migrations and `python -m app.seed` first);
    otherwise the in-memory sample data, for local runs without a database."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return seeded_store()
    from .db import make_engine
    from .sql_store import SqlStore

    return SqlStore(make_engine(url))


def create_app(store: DataStore | None = None, gateway: Gateway | None = None) -> FastAPI:
    app = FastAPI(title="SecureFin API")
    app.state.store = store or default_store()
    app.state.gateway = gateway or build_gateway()
    app.include_router(router)
    app.include_router(internal_router)
    return app


app = create_app()
