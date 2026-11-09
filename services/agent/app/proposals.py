"""Turn the model's free-form proposal into a checked ProposedAction. The agent never executes anything:
a valid proposal goes back to the api, which sends it to the gateway."""
from pydantic import ValidationError
from securefin_contracts import ProposedAction, ToolName
from securefin_contracts.actions import CreatePaymentParams


def to_proposed_action(proposal: dict | None) -> ProposedAction | None:
    """None when there is no proposal or it does not fit create_payment_request exactly
    (unknown fields such as an IBAN or beneficiary make it invalid)."""
    if not proposal:
        return None
    try:
        if proposal.get("tool") != ToolName.CREATE_PAYMENT_REQUEST.value:
            return None
        params = CreatePaymentParams.model_validate(proposal.get("params") or {})
        return ProposedAction(tool=ToolName.CREATE_PAYMENT_REQUEST, params=params.model_dump(mode="json"),
                              rationale=str(proposal.get("rationale", ""))[:1000])
    except (ValidationError, AttributeError, TypeError):
        return None
