"""Replay protection for /v1/authorize, keyed by request_id.

Same request_id + same payload  -> the first decision is returned again (safe retry).
Same request_id + other payload -> conflict (a replayed or tampered request).
"""
import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from securefin_contracts import AuthorizeRequest, GatewayDecision


class RequestIdConflictError(RuntimeError):
    """This request_id was already used with a different payload."""


def fingerprint(req: AuthorizeRequest) -> str:
    canonical = json.dumps(req.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyCache:
    def __init__(self, max_items: int = 10_000, ttl_seconds: float = 24 * 3600,
                 clock: Callable[[], float] = time.monotonic):
        self._items: OrderedDict[tuple[int, int, str], tuple[str, GatewayDecision, float]] = OrderedDict()
        self._max, self._ttl, self._clock = max_items, ttl_seconds, clock
        self._lock = threading.Lock()

    @staticmethod
    def _key(req: AuthorizeRequest) -> tuple[int, int, str]:
        return (req.company_id, req.user_id, req.request_id)

    def get(self, req: AuthorizeRequest) -> GatewayDecision | None:
        with self._lock:
            entry = self._items.get(self._key(req))
            if entry is None:
                return None
            fp, decision, stored_at = entry
            if self._clock() - stored_at > self._ttl:
                del self._items[self._key(req)]
                return None
            if fp != fingerprint(req):
                raise RequestIdConflictError(req.request_id)
            return decision

    def put(self, req: AuthorizeRequest, decision: GatewayDecision) -> None:
        with self._lock:
            self._items[self._key(req)] = (fingerprint(req), decision, self._clock())
            while len(self._items) > self._max:
                self._items.popitem(last=False)
