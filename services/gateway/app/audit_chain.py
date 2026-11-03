"""entry_hash[n] = SHA256(canonical(entry_data[n]) + entry_hash[n-1])"""
import hashlib
import json

GENESIS = "0" * 64


def compute_hash(entry_data: dict, prev_hash: str) -> str:
    canonical = json.dumps(entry_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((canonical + prev_hash).encode()).hexdigest()


def verify_chain(entries: list[dict]) -> int | None:
    """Return the index of the first broken entry, or None if the chain is intact."""
    prev = GENESIS
    for i, e in enumerate(entries):
        data = {k: v for k, v in e.items() if k not in ("prev_hash", "entry_hash", "id")}
        if e["prev_hash"] != prev or compute_hash(data, prev) != e["entry_hash"]:
            return i
        prev = e["entry_hash"]
    return None
