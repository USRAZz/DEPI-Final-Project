import app.main as main
import pytest
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
