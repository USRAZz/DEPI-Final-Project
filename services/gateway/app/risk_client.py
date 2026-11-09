"""Client for the risk service (POST /v1/score). Any failure means 'unavailable' (fail closed)."""
import os

import httpx
from pydantic import ValidationError
from securefin_contracts import RiskRequest, RiskScore

DEFAULT_RISK_URL = "http://risk:8000"  # docker service name; use http://localhost:8003 outside Docker


class RiskUnavailableError(RuntimeError):
    """The risk service was down, too slow, or returned something unusable."""


class RiskClient:
    def __init__(self, base_url: str, timeout_s: float, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def score(self, invoice_id: int) -> RiskScore:
        try:
            resp = self._client.post("/v1/score", json=RiskRequest(invoice_id=invoice_id).model_dump())
            resp.raise_for_status()
            return RiskScore.model_validate_json(resp.content)
        except (httpx.HTTPError, ValidationError, ValueError) as e:
            raise RiskUnavailableError(type(e).__name__) from e


def build_risk_client(timeout_ms: int) -> RiskClient:
    return RiskClient(os.environ.get("RISK_URL", DEFAULT_RISK_URL), timeout_ms / 1000)
