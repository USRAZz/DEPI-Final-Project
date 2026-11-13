"""Reads a payment request from the api (GET /payments/{id}). The gateway never reads api tables directly."""
import os
from datetime import UTC

import httpx
from pydantic import ValidationError
from securefin_contracts import PaymentRequestInfo

DEFAULT_API_URL = "http://api:8000"  # docker service name; use http://localhost:8000 outside Docker


class PaymentsUnavailableError(RuntimeError):
    """The api was down, too slow, or returned something unusable."""


class PaymentNotFoundError(LookupError):
    """The api says this payment request does not exist."""


class PaymentsClient:
    def __init__(self, base_url: str, timeout_s: float, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def get(self, payment_request_id: int) -> PaymentRequestInfo:
        try:
            resp = self._client.get(f"/payments/{payment_request_id}")
            if resp.status_code == 404:
                raise PaymentNotFoundError(payment_request_id)
            resp.raise_for_status()
            info = PaymentRequestInfo.model_validate_json(resp.content)
            if info.created_at.tzinfo is None:  # treat a timestamp without a zone as UTC
                info = info.model_copy(update={"created_at": info.created_at.replace(tzinfo=UTC)})
            return info
        except PaymentNotFoundError:
            raise
        except (httpx.HTTPError, ValidationError, ValueError) as e:
            raise PaymentsUnavailableError(type(e).__name__) from e


def build_payments_client(timeout_ms: int) -> PaymentsClient:
    return PaymentsClient(os.environ.get("API_URL", DEFAULT_API_URL), timeout_ms / 1000)
