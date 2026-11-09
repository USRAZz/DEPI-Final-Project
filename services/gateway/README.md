## Risk service

`/v1/authorize` calls the risk service (`POST /v1/score`, sends `invoice_id`) for payment requests.

- Score >= `risk.hold_score` (70) -> `PENDING_APPROVAL`, reason "high risk score"
- Risk service down, slower than `gateway.timeout_ms`, or bad response -> `PENDING_APPROVAL`, reason "risk service unavailable" (fail closed, never ALLOW)
- Address: env `RISK_URL`. Default `http://risk:8000` (Docker). Local run without Docker: `RISK_URL=http://localhost:8003`
