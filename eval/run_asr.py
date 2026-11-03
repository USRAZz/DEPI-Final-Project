"""ASR experiment skeleton (owner: M4 Ziad). ASR = unsafe actions executed / attack cases."""
import json
import pathlib

CASES = sorted(pathlib.Path(__file__).parent.joinpath("attack_suite").glob("*.json"))


def run_case(case: dict, gateway_enabled: bool) -> bool:
    """Return True if the attack succeeded (an unsafe action was executed). TODO: call api /chat + /payments."""
    raise NotImplementedError


if __name__ == "__main__":
    print(f"{len(CASES)} attack cases found. Implement run_case() to compute ASR baseline vs gateway.")
    for c in CASES:
        json.loads(c.read_text())
