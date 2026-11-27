import app.main as main
import pytest
from app.audit_log import InMemoryAuditLog
from app.idempotency import IdempotencyCache
from securefin_contracts import RiskLevel, RiskScore


class FakeRisk:
    def __init__(self, score: float = 10):
        self.value = score

    def score(self, invoice_id: int) -> RiskScore:
        return RiskScore(score=self.value, level=RiskLevel.LOW)


@pytest.fixture(autouse=True)
def low_risk(monkeypatch):
    """Default for every test: risk service answers LOW. Tests that care override main.RISK_CLIENT."""
    monkeypatch.setattr(main, "RISK_CLIENT", FakeRisk(10))


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Every test starts with an empty request_id cache and an empty in-memory audit log."""
    monkeypatch.setattr(main, "IDEMPOTENCY", IdempotencyCache())
    monkeypatch.setattr(main, "AUDIT_LOG", InMemoryAuditLog())


@pytest.fixture(autouse=True)
def no_service_token_by_default():
    """Existing tests call the endpoints directly. The service-token tests remove this override."""
    main.app.dependency_overrides[main.require_service_token] = lambda: None
    yield
    main.app.dependency_overrides.clear()
