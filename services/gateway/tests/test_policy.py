from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from app.policy import PolicyError, find_policy_dir, load_gateway_policy
from securefin_contracts import Role, ToolName

REAL = find_policy_dir()

# Independent copy of the allowlist that used to be hard-coded in main.py.
OLD_ALLOWLIST = {
    Role.VIEWER: {ToolName.GET_INVOICES, ToolName.GET_TRANSACTIONS, ToolName.GENERATE_REPORT},
    Role.ACCOUNTANT: {ToolName.GET_INVOICES, ToolName.GET_TRANSACTIONS, ToolName.CHECK_DUPLICATE,
                      ToolName.GET_RISK_SCORE, ToolName.CREATE_PAYMENT_REQUEST, ToolName.GENERATE_REPORT},
    Role.APPROVER: {ToolName.GET_INVOICES, ToolName.GET_TRANSACTIONS, ToolName.GET_RISK_SCORE,
                    ToolName.GENERATE_REPORT},
    Role.ADMIN: set(ToolName),
}


@pytest.fixture
def pdir(tmp_path: Path) -> Path:
    for name in ("defaults.yaml", "role_tools.yaml"):
        (tmp_path / name).write_text((REAL / name).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def _edit(pdir: Path, name: str, fn):
    data = yaml.safe_load((pdir / name).read_text(encoding="utf-8"))
    fn(data)
    (pdir / name).write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.mark.parametrize("role", list(Role))
def test_role_tools_match_previous_allowlist(role):
    policy = load_gateway_policy(REAL)
    assert set(policy.tools_for(role)) == OLD_ALLOWLIST[role]


def test_every_role_is_defined():
    policy = load_gateway_policy(REAL)
    assert set(policy.role_tools.roles) == set(Role)


def test_role_missing_from_file_gets_no_tools(pdir):
    _edit(pdir, "role_tools.yaml", lambda d: d["roles"].pop("viewer"))
    assert load_gateway_policy(pdir).tools_for(Role.VIEWER) == frozenset()


@pytest.mark.parametrize(("amount", "currency", "expected"), [
    ("500", "EGP", 1),
    ("10000", "EGP", 1),       # strictly above: the threshold itself needs one approver
    ("10000.01", "EGP", 2),
    ("25000", "EGP", 2),
    ("1", "USD", 2),           # no FX rate in policy: foreign currency always needs two
])
def test_required_approvers(amount, currency, expected):
    assert load_gateway_policy(REAL).required_approvers(Decimal(amount), currency) == expected


def test_threshold_comes_from_the_file(pdir):
    _edit(pdir, "defaults.yaml", lambda d: d["approvals"].update(two_approver_threshold_egp=100))
    assert load_gateway_policy(pdir).required_approvers(Decimal("101"), "EGP") == 2


@pytest.mark.parametrize("mutate", [
    lambda d: d["approvals"].update(creator_can_approve=True),
    lambda d: d["gateway"].update(fail_mode="allow"),
    lambda d: d["assistant"].update(can_execute=True),
    lambda d: d["assistant"].update(can_approve=True),
    lambda d: d["risk"].update(on_risk_service_unavailable="allow"),
    lambda d: d["risk"].update(hold_score=101),
    lambda d: d["approvals"].update(two_approver_threshold_egp=0),
    lambda d: d["bank_details"].update(confirmation_required=False),
    lambda d: d.update(unknown_key=1),
])
def test_unsafe_or_unknown_defaults_refused(pdir, mutate):
    _edit(pdir, "defaults.yaml", mutate)
    with pytest.raises(PolicyError):
        load_gateway_policy(pdir)


@pytest.mark.parametrize("mutate", [
    lambda d: d["roles"]["viewer"].append("delete_everything"),
    lambda d: d["roles"].update(superuser=["get_invoices"]),
    lambda d: d["roles"]["viewer"].append("get_invoices"),
])
def test_bad_role_tools_refused(pdir, mutate):
    _edit(pdir, "role_tools.yaml", mutate)
    with pytest.raises(PolicyError):
        load_gateway_policy(pdir)


def test_missing_file_refused(pdir):
    (pdir / "role_tools.yaml").unlink()
    with pytest.raises(PolicyError):
        load_gateway_policy(pdir)


def test_broken_yaml_refused(pdir):
    (pdir / "defaults.yaml").write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(PolicyError):
        load_gateway_policy(pdir)


def test_non_mapping_yaml_refused(pdir):
    (pdir / "defaults.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        load_gateway_policy(pdir)


def test_policy_dir_env_override(monkeypatch, pdir):
    monkeypatch.setenv("POLICY_DIR", str(pdir))
    assert find_policy_dir() == pdir
