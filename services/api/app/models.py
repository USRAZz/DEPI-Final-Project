"""Records only the api stores. Not shared shapes, so they live here and not in contracts/."""

from pydantic import ConfigDict, Field
from securefin_contracts import PaymentRequestInfo

_INFO_FIELDS = set(PaymentRequestInfo.model_fields)


class PaymentRecord(PaymentRequestInfo):
    """A row of the api's payment_requests table: the gateway's PaymentRequestInfo plus what only the api needs."""

    model_config = ConfigDict(extra="forbid")

    bank_account_id: int
    note: str = Field(default="", max_length=500)

    def info(self) -> PaymentRequestInfo:
        """What the gateway reads through GET /payments/{id}."""
        return PaymentRequestInfo.model_validate(self.model_dump(include=_INFO_FIELDS))
