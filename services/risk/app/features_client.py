"""Fetches an invoice's risk features from services/api. Any failure means 'unavailable' (fail closed).

The api owns invoices and vendors; this service never reads their tables. The call is service-to-service
(no user session), so it carries the shared INTERNAL_SERVICE_TOKEN in the X-Service-Token header.
"""
import os

import httpx
from pydantic import ValidationError
from securefin_contracts import RiskFeatures

DEFAULT_API_URL = "http://api:8000"  # docker service name; use http://localhost:8000 outside Docker
# The gateway waits at most 2000 ms for the whole risk call, so this fetch must finish well inside that.
DEFAULT_TIMEOUT_MS = 1200
PATH = "/v1/invoices/{invoice_id}/risk-features"


class FeaturesUnavailableError(RuntimeError):
    """The api was down, too slow, refused us, or returned something unusable."""


class FeaturesClient:
    def __init__(self, base_url: str, token: str, timeout_s: float, transport: httpx.BaseTransport | None = None):
        self._token = token
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def fetch(self, invoice_id: int) -> RiskFeatures:
        if not self._token:
            raise FeaturesUnavailableError("INTERNAL_SERVICE_TOKEN is not set")
        try:
            resp = self._client.get(PATH.format(invoice_id=invoice_id), headers={"X-Service-Token": self._token})
            resp.raise_for_status()
            return RiskFeatures.model_validate_json(resp.content)
        except (httpx.HTTPError, ValidationError, ValueError) as e:
            raise FeaturesUnavailableError(type(e).__name__) from e


def build_features_client() -> FeaturesClient:
    return FeaturesClient(
        os.environ.get("API_URL", DEFAULT_API_URL),
        os.environ.get("INTERNAL_SERVICE_TOKEN", ""),
        int(os.environ.get("RISK_FEATURES_TIMEOUT_MS", DEFAULT_TIMEOUT_MS)) / 1000,
    )
