from fastapi import FastAPI

from .gateway import Gateway, build_gateway
from .risk_features import internal_router
from .routes import router
from .store import Store, seeded_store


def create_app(store: Store | None = None, gateway: Gateway | None = None) -> FastAPI:
    app = FastAPI(title="SecureFin API")
    app.state.store = store or seeded_store()
    app.state.gateway = gateway or build_gateway()
    app.include_router(router)
    app.include_router(internal_router)
    return app


app = create_app()
