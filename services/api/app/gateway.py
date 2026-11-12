"""Client for services/gateway's approval endpoints.

The api never decides on a payment itself: approvals go to POST /v1/approvals/{id} and
execution needs POST /v1/execute-check to say allowed. Anything the client cannot read
as a clear answer is GatewayUnavailable, and the caller treats it as "not approved".
"""

import os
from typing import Protocol

import httpx
from pydantic import ValidationError
from securefin_contracts import ApprovalRequest, ApprovalResult, ExecuteCheckRequest, ExecuteCheckResult

DEFAULT_GATEWAY_URL = "http://gateway:8000"  # docker service name; use http://localhost:8001 outside Docker
DEFAULT_TIMEOUT_S = 5.0

# Status codes on which the gateway answered on purpose, with reasons in `detail`.
_REFUSALS = {403, 404, 409, 422}


class GatewayUnavailable(Exception):
    """The gateway was down, too slow, or answered with something unusable. Nothing was approved."""


class ApprovalRefused(Exception):
    def __init__(self, status_code: int, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.status_code = status_code
        self.reasons = reasons


class Gateway(Protocol):
    def submit_approval(self, req: ApprovalRequest) -> ApprovalResult: ...
    def execute_check(self, req: ExecuteCheckRequest) -> ExecuteCheckResult: ...


def _reasons(resp: httpx.Response) -> list[str]:
    try:
        detail = resp.json().get("detail")
    except (ValueError, AttributeError):
        return [f"gateway refused (HTTP {resp.status_code})"]
    if isinstance(detail, list):
        return [d if isinstance(d, str) else str(d.get("msg", d)) for d in detail]
    return [str(detail)] if detail else [f"gateway refused (HTTP {resp.status_code})"]


class HttpGateway:
    def __init__(self, base_url: str, timeout_s: float = DEFAULT_TIMEOUT_S, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def _post(self, path: str, body, result_type):
        try:
            resp = self._client.post(path, json=body.model_dump(mode="json"))
        except httpx.HTTPError as e:
            raise GatewayUnavailable(type(e).__name__) from e
        if resp.status_code in _REFUSALS:
            raise ApprovalRefused(resp.status_code, _reasons(resp))
        if resp.status_code != 200:
            raise GatewayUnavailable(f"HTTP {resp.status_code}: {'; '.join(_reasons(resp))}")
        try:
            return result_type.model_validate_json(resp.content)
        except ValidationError as e:
            raise GatewayUnavailable("unreadable answer") from e

    def submit_approval(self, req: ApprovalRequest) -> ApprovalResult:
        return self._post(f"/v1/approvals/{req.payment_request_id}", req, ApprovalResult)

    def execute_check(self, req: ExecuteCheckRequest) -> ExecuteCheckResult:
        return self._post("/v1/execute-check", req, ExecuteCheckResult)


def build_gateway() -> HttpGateway:
    timeout_s = float(os.environ.get("GATEWAY_TIMEOUT_MS", DEFAULT_TIMEOUT_S * 1000)) / 1000
    return HttpGateway(os.environ.get("GATEWAY_URL", DEFAULT_GATEWAY_URL), timeout_s)
