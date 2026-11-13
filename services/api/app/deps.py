import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from securefin_contracts import User

from .gateway import Gateway
from .store import DataStore


def get_store(request: Request) -> DataStore:
    return request.app.state.store


def get_gateway(request: Request) -> Gateway:
    return request.app.state.gateway


def dev_login_enabled() -> bool:
    """On by default locally; on a Vercel deployment only when DEV_LOGIN=1 is set on purpose."""
    return not os.environ.get("VERCEL") or os.environ.get("DEV_LOGIN") == "1"


def current_user(
    store: Annotated[DataStore, Depends(get_store)],
    x_user_id: Annotated[int | None, Header()] = None,
) -> User:
    # Development login: the caller names its user in X-User-Id. Anyone who can reach the
    # api can claim any user, so it is off on public deployments. Replaced by JWT.
    if not dev_login_enabled():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in is not available on this deployment")
    user = store.user(x_user_id) if x_user_id is not None else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    return user


StoreDep = Annotated[DataStore, Depends(get_store)]
GatewayDep = Annotated[Gateway, Depends(get_gateway)]
UserDep = Annotated[User, Depends(current_user)]
