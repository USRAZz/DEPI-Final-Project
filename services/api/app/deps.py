from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from securefin_contracts import User

from .gateway import Gateway
from .store import Store


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_gateway(request: Request) -> Gateway:
    return request.app.state.gateway


def current_user(
    store: Annotated[Store, Depends(get_store)],
    x_user_id: Annotated[int | None, Header()] = None,
) -> User:
    # Development login: the caller names its user in X-User-Id.
    # Replaced by JWT (weeks 3-5); never enable this outside local development.
    user = store.user(x_user_id) if x_user_id is not None else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    return user


StoreDep = Annotated[Store, Depends(get_store)]
GatewayDep = Annotated[Gateway, Depends(get_gateway)]
UserDep = Annotated[User, Depends(current_user)]
