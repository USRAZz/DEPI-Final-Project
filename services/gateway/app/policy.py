"""Gateway policy: loaded from policies/*.yaml, validated strictly, fail closed.

A bad or missing policy file raises PolicyError at start-up, so the gateway
refuses to run instead of running with weaker rules.
"""
import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from securefin_contracts import Role, ToolName

BASE_CURRENCY = "EGP"


class PolicyError(RuntimeError):
    """The policy could not be loaded or is unsafe."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Approvals(_Strict):
    two_approver_threshold_egp: Decimal = Field(gt=0)
    creator_can_approve: Literal[False]  # maker-checker: never allowed
    approval_expiry_hours: int = Field(gt=0)


class BankDetails(_Strict):
    change_hold_hours: int = Field(gt=0)
    confirmation_required: Literal[True]


class Risk(_Strict):
    hold_score: float = Field(ge=0, le=100)
    on_risk_service_unavailable: Literal["hold"]


class GatewaySettings(_Strict):
    timeout_ms: int = Field(gt=0)
    fail_mode: Literal["block"]  # never fail open


class AssistantLimits(_Strict):
    can_execute: Literal[False]
    can_approve: Literal[False]
    max_steps: int = Field(gt=0)


class Defaults(_Strict):
    version: int
    approvals: Approvals
    bank_details: BankDetails
    risk: Risk
    gateway: GatewaySettings
    assistant: AssistantLimits


class RoleTools(_Strict):
    version: int
    roles: dict[Role, frozenset[ToolName]]

    @field_validator("roles", mode="before")
    @classmethod
    def _no_duplicates(cls, v):
        if isinstance(v, dict):
            for role, tools in v.items():
                if isinstance(tools, list) and len(tools) != len(set(tools)):
                    raise ValueError(f"duplicate tool in role '{role}'")
        return v


class GatewayPolicy(_Strict):
    defaults: Defaults
    role_tools: RoleTools

    def tools_for(self, role: Role) -> frozenset[ToolName]:
        """Tools a role may call. A role missing from the file gets nothing."""
        return self.role_tools.roles.get(role, frozenset())

    def required_approvers(self, amount: Decimal, currency: str) -> int:
        """2 above the threshold; any non-EGP amount always needs 2 (no FX rate in policy)."""
        if currency != BASE_CURRENCY:
            return 2
        return 2 if amount > self.defaults.approvals.two_approver_threshold_egp else 1


def find_policy_dir() -> Path:
    """POLICY_DIR env var, else the nearest parent folder holding policies/defaults.yaml."""
    env = os.environ.get("POLICY_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        if (parent / "policies" / "defaults.yaml").is_file():
            return parent / "policies"
    raise PolicyError("policies/ folder not found; set POLICY_DIR")


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise PolicyError(f"cannot read {path.name}: {e}") from e
    if not isinstance(data, dict):
        raise PolicyError(f"{path.name} must contain a mapping")
    return data


def load_gateway_policy(policy_dir: Path | None = None) -> GatewayPolicy:
    d = policy_dir or find_policy_dir()
    try:
        return GatewayPolicy(
            defaults=Defaults.model_validate(_read_yaml(d / "defaults.yaml")),
            role_tools=RoleTools.model_validate(_read_yaml(d / "role_tools.yaml")),
        )
    except ValidationError as e:
        raise PolicyError(f"invalid policy: {e.error_count()} error(s): {e}") from e


@lru_cache(maxsize=1)
def get_policy() -> GatewayPolicy:
    return load_gateway_policy()
