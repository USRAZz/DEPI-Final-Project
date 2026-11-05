"""Approval decisions for the screens, until services/gateway serves them.

LocalGateway implements the agreed rules in process so the API and frontend can be
built against them. The API never decides on its own: it asks the gateway, and if
the gateway fails, the answer is BLOCK (fail closed).
"""

import hashlib
import hmac
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from securefin_contracts import (
    ApprovalPayload,
    ApprovalRecord,
    BankAccount,
    Decision,
    GatewayDecision,
    Money,
    PaymentRequest,
    RiskLevel,
    RiskScore,
    User,
)

DUAL_APPROVAL_LIMIT = Decimal(os.getenv("DUAL_APPROVAL_THRESHOLD_EGP", "10000"))


class ApprovalRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Gateway(Protocol):
    def decide(self, request: PaymentRequest, risk: RiskScore | None) -> GatewayDecision: ...
    def approvals(self, request_id: int) -> list[ApprovalRecord]: ...
    def record(self, request: PaymentRequest, account: BankAccount, approver: User, approved: bool) -> ApprovalRecord: ...


class LocalGateway:
    def __init__(self, signing_key: bytes):
        self._key = signing_key
        self._approvals: dict[int, list[ApprovalRecord]] = {}

    def approvals(self, request_id: int) -> list[ApprovalRecord]:
        return list(self._approvals.get(request_id, []))

    def decide(self, request: PaymentRequest, risk: RiskScore | None) -> GatewayDecision:
        reasons: list[str] = []
        required = 1
        if request.money.amount > DUAL_APPROVAL_LIMIT:
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

    def record(self, request: PaymentRequest, account: BankAccount, approver: User, approved: bool) -> ApprovalRecord:
        if approver.id == request.created_by:
            raise ApprovalRefused("SELF_APPROVAL")
        if any(r.approver_id == approver.id for r in self._approvals.get(request.id, [])):
            raise ApprovalRefused("ALREADY_DECIDED")

        signed_at = datetime.now(UTC)
        record = ApprovalRecord(
            payment_request_id=request.id, approver_id=approver.id, approve=approved, signed_at=signed_at,
            hmac_signature=self._sign(ApprovalPayload(
                payment_request_id=request.id, money=request.money, iban=account.iban,
                approver_id=approver.id, signed_at=signed_at,
            )),
        )
        self._approvals.setdefault(request.id, []).append(record)
        return record

    def _sign(self, payload: ApprovalPayload) -> str:
        # Placeholder HMAC until Anan settles the signature format.
        return hmac.new(self._key, payload.model_dump_json().encode(), hashlib.sha256).hexdigest()

    def verify(self, record: ApprovalRecord, money: Money, iban: str) -> bool:
        """True only if the signature covers exactly this amount and account."""
        expected = self._sign(ApprovalPayload(
            payment_request_id=record.payment_request_id, money=money, iban=iban,
            approver_id=record.approver_id, signed_at=record.signed_at,
        ))
        return hmac.compare_digest(expected, record.hmac_signature)
