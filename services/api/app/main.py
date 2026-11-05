import os
import secrets

from fastapi import FastAPI

from .gateway import Gateway, LocalGateway
from .routes import router
from .store import Store, seeded_store


def create_app(store: Store | None = None, gateway: Gateway | None = None) -> FastAPI:
    app = FastAPI(title="SecureFin API")
    app.state.store = store or seeded_store()
    signing_key = os.environ.get("HMAC_SECRET", "").encode() or secrets.token_bytes(32)
    app.state.gateway = gateway or LocalGateway(signing_key)
    app.include_router(router)
    return app


app = create_app()
