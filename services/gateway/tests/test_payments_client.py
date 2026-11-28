import httpx
import pytest
from app.payments_client import PaymentNotFoundError, PaymentsClient, PaymentsUnavailableError

GOOD = {"id": 4, "company_id": 1, "creator_id": 7, "invoice_id": 2, "vendor_id": 3, "amount": "500.00",
        "currency": "EGP", "status": "PENDING_APPROVAL", "created_at": "2026-11-10T10:00:00Z"}


def _pc(handler, token="secret"):
    return PaymentsClient("http://api", token, 1, transport=httpx.MockTransport(handler))


def test_parses_payment_and_calls_right_path_with_the_service_token():
    seen = {}

    def handler(req):
        seen["url"], seen["token"] = str(req.url), req.headers.get("X-Service-Token")
        return httpx.Response(200, json=GOOD)

    p = _pc(handler).get(4)
    assert seen["url"].endswith("/payments/4") and seen["token"] == "secret" and p.creator_id == 7


def test_missing_token_is_unavailable_without_calling_the_api():
    calls = []
    with pytest.raises(PaymentsUnavailableError):
        _pc(lambda req: calls.append(req) or httpx.Response(200, json=GOOD), token="").get(4)
    assert calls == []


def test_404_is_not_found():
    with pytest.raises(PaymentNotFoundError):
        _pc(lambda req: httpx.Response(404)).get(4)


@pytest.mark.parametrize("handler", [
    lambda req: httpx.Response(401),  # the api refused our service token
    lambda req: httpx.Response(500),
    lambda req: httpx.Response(503, json=GOOD),
    lambda req: httpx.Response(200, text="nope"),
    lambda req: httpx.Response(200, json={"id": 4}),
    lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("slow")),
])
def test_failures_become_unavailable(handler):
    with pytest.raises(PaymentsUnavailableError):
        _pc(handler).get(4)


def test_naive_timestamp_is_treated_as_utc():
    naive = {**GOOD, "created_at": "2026-11-10T10:00:00"}
    p = _pc(lambda req: httpx.Response(200, json=naive)).get(4)
    assert p.created_at.utcoffset().total_seconds() == 0
