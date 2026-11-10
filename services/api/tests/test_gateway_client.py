import httpx
import pytest
from app.gateway import ApprovalRefused, GatewayUnavailable, HttpGateway
from securefin_contracts import ApprovalRequest, ExecuteCheckRequest

APPROVAL = ApprovalRequest(payment_request_id=187, approver_id=2, approve=True, approver_role="approver", company_id=1)
CHECK = ExecuteCheckRequest(payment_request_id=187, requested_by=3, company_id=1)
RESULT = {"payment_request_id": 187, "status": "PENDING_APPROVAL", "approvals_received": 1, "approvals_required": 2,
          "reasons": [], "audit_entry_id": None}


def gateway_answering(handler):
    return HttpGateway("http://gateway", transport=httpx.MockTransport(handler))


def test_posts_the_approval_to_the_gateway():
    seen = {}

    def handler(request: httpx.Request):
        seen["path"], seen["body"] = request.url.path, request.read()
        return httpx.Response(200, json=RESULT)

    result = gateway_answering(handler).submit_approval(APPROVAL)
    assert seen["path"] == "/v1/approvals/187"
    assert ApprovalRequest.model_validate_json(seen["body"]) == APPROVAL
    assert result.approvals_received == 1


@pytest.mark.parametrize("code", [403, 404, 409, 422])
def test_refusals_carry_the_gateways_reasons(code):
    gw = gateway_answering(lambda r: httpx.Response(code, json={"detail": ["maker-checker: no"]}))
    with pytest.raises(ApprovalRefused) as refused:
        gw.submit_approval(APPROVAL)
    assert refused.value.status_code == code and refused.value.reasons == ["maker-checker: no"]


@pytest.mark.parametrize("response", [
    httpx.Response(503, json={"detail": ["approval signing unavailable: nothing approved"]}),
    httpx.Response(500, text="boom"),
    httpx.Response(200, json={"unexpected": True}),
    httpx.Response(200, text="not json"),
])
def test_anything_unclear_is_unavailable(response):
    gw = gateway_answering(lambda r: response)
    with pytest.raises(GatewayUnavailable):
        gw.submit_approval(APPROVAL)
    with pytest.raises(GatewayUnavailable):
        gw.execute_check(CHECK)


def test_network_errors_are_unavailable():
    def handler(request):
        raise httpx.ConnectTimeout("too slow", request=request)

    with pytest.raises(GatewayUnavailable):
        gateway_answering(handler).execute_check(CHECK)


def test_execute_check_reads_allowed():
    gw = gateway_answering(lambda r: httpx.Response(200, json={"allowed": False, "reasons": ["rejected"]}))
    result = gw.execute_check(CHECK)
    assert result.allowed is False and result.reasons == ["rejected"]
