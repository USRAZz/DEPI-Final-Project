"""Every attack case is well-formed, so run_asr.py can score it without special cases."""
import json
import pathlib

SUITE = pathlib.Path(__file__).resolve().parents[1] / "eval" / "attack_suite"
CATEGORIES = {"A": "prompt_injection", "B": "self_approval", "C": "iban_swap", "D": "audit_tamper"}
INPUT_TYPES = {"invoice_text", "chat_message", "api_sequence", "proposed_action", "sql"}
EXPECTED = {"BLOCK", "PENDING_APPROVAL", "NEEDS-REVIEW", "FLAGGED", "VENDOR_CHANGE_PENDING", "DENIED", "CHAIN_BROKEN"}


def _cases():
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(SUITE.glob("ATK-*.json"))]


def test_cases_are_well_formed():
    cases = _cases()
    assert len(cases) >= 21
    for path, c in cases:
        assert c["id"] == path.stem
        assert CATEGORIES[c["scenario"]] == c["category"], c["id"]
        assert c["input"]["type"] in INPUT_TYPES, c["id"]
        assert c["expected"] in EXPECTED, c["id"]
        assert c["description"].strip() and c["unsafe_if"].strip(), c["id"]


def test_every_category_is_covered():
    seen = {c["category"] for _, c in _cases()}
    assert seen == set(CATEGORIES.values())
