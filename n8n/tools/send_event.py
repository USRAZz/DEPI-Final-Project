"""Send one signed decision event to the n8n notification webhook (demo and manual tests).

This is also the reference for the gateway side: the signature is
    X-SecureFin-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>
    X-SecureFin-Timestamp: <unix seconds>
The secret is N8N_WEBHOOK_HMAC_SECRET. It must NOT be the approval signing key.

    python n8n/tools/send_event.py hold --payment 123 --reason VENDOR_ACCOUNT_MISMATCH
    python n8n/tools/send_event.py bank_change_pending --vendor 45
"""
import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid

TYPES = ["hold", "block", "needs_second_approval", "bank_change_pending"]


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("event_type", choices=TYPES)
    p.add_argument("--payment", type=int, help="payment_request_id")
    p.add_argument("--vendor", type=int, help="vendor_id (bank_change_pending)")
    p.add_argument("--reason", action="append", default=[], help="reason code; repeat for more")
    p.add_argument("--expires-at", help="ISO time shown as 'until'")
    p.add_argument("--event-id", default=None, help="reuse an id to test duplicate handling")
    p.add_argument("--url", default=os.getenv("N8N_DECISION_WEBHOOK_URL",
                                             "http://localhost:5678/webhook/securefin/decision-events"))
    p.add_argument("--age", type=int, default=0, help="make the timestamp this many seconds old")
    a = p.parse_args()
    secret = os.environ["N8N_WEBHOOK_HMAC_SECRET"]
    event = {"event_id": a.event_id or str(uuid.uuid4()), "event_type": a.event_type, "company_id": 1,
             "payment_request_id": a.payment, "vendor_id": a.vendor, "reasons": a.reason, "expires_at": a.expires_at}
    body = json.dumps(event, ensure_ascii=False).encode()
    ts = str(int(time.time()) - a.age)
    req = urllib.request.Request(a.url, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-SecureFin-Timestamp": ts,
        "X-SecureFin-Signature": sign(secret, ts, body)})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(r.status, r.read().decode())
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
