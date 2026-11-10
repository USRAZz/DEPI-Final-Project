"""Approval decisions for the screens, until services/gateway serves them.

LocalGateway implements the agreed rules in process so the API and frontend can be
built against them. The API never decides on its own: it asks the gateway, and if
the gateway fails, the answer is BLOCK (fail closed).
"""

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from securefin_contracts import ApprovalRecord, BankAccount, Decision, GatewayDecision, RiskLevel, RiskScore, User

from .models import PaymentRecord

DUAL_APPROVAL_LIMIT = Decimal(os.getenv("DUAL_APPROVAL_THRESHOLD_EGP", "10000"))


class ApprovalRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Gateway(Protocol):
    def decide(self, request: PaymentRecord, risk: RiskScore | None) -> GatewayDecision: ...
    def approvals(self, request_id: int) -> list[ApprovalRecord]: ...
    def record(self, request: PaymentRecord, account: BankAccount, approver: User, approved: bool) -> ApprovalRecord: ...


class LocalGateway:
    def __init__(self, signing_key: bytes):
        self._key = signing_key
        self._approvals: dict[int, list[ApprovalRecord]] = {}

    def approvals(self, request_id: int) -> list[ApprovalRecord]:
        return list(self._approvals.get(request_id, []))

    def decide(self, request: PaymentRecord, risk: RiskScore | None) -> GatewayDecision:
        reasons: list[str] = []
        required = 1
        if request.amount > DUAL_APPROVAL_LIMIT:
            required = 2
            reasons.append("ABOVE_DUAL_APPROVAL_LIMIT")
        if risk is None:
            reasons.append("RISK_NOT_ASSESSED")
        elif risk.level == RiskLevel.HIGH:
            reasons.append("HIGH_RISK")

        records = self._approvals.get(request.id, [])
        if any(not r.approve for r in records):
            decision = Decision.BLOCK
            reasons.append("REJECTED_BY_APPROVER")
        elif risk is not None and sum(r.approve for r in records) >= required:
            decision = Decision.ALLOW
        else:
            decision = Decision.PENDING_APPROVAL

        return GatewayDecision(
            decision=decision, reasons=reasons, required_approvers=required,
            risk_score=risk.score if risk else None,
        )

    def record(self, request: PaymentRecord, account: BankAccount, approver: User, approved: bool) -> ApprovalRecord:
        if approver.id == request.creator_id:
            raise ApprovalRefused("SELF_APPROVAL")
        if any(r.approver_id == approver.id for r in self._approvals.get(request.id, [])):
            raise ApprovalRefused("ALREADY_DECIDED")

        signed_at = datetime.now(UTC)
        record = ApprovalRecord(
            payment_request_id=request.id, approver_id=approver.id, approve=approved, signed_at=signed_at,
            hmac_signature=self._sign(request.id, request.amount, request.currency, account.iban, approver.id, signed_at),
        )
        self._approvals.setdefault(request.id, []).append(record)
        return record

    def _sign(self, request_id: int, amount: Decimal, currency: str, iban: str, approver_id: int,
              signed_at: datetime) -> str:
        # Placeholder HMAC over exactly what is approved: the amount and the account.
        payload = json.dumps([request_id, str(amount), currency, iban, approver_id, signed_at.isoformat()])
        return hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()

    def verify(self, record: ApprovalRecord, amount: Decimal, currency: str, iban: str) -> bool:
        """True only if the signature covers exactly this amount and account."""
        expected = self._sign(record.payment_request_id, amount, currency, iban, record.approver_id, record.signed_at)
        return hmac.compare_digest(expected, record.hmac_signature)
