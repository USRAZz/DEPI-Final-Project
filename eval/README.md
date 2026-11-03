# eval/ — Evaluation harness (owner: M4 Ziad)

- `attack_suite/` — labelled malicious documents & prompts (target 50–100). One JSON per case:
  `{"id": "ATK-001", "scenario": "A", "input": {...}, "unsafe_if": "create_payment_request to non-verified IBAN"}`
- `legit_set/` — normal requests & invoices (measures false-block rate).
- `run_asr.py` — runs every case twice: `GATEWAY_ENABLED=false` (baseline) and `true`; writes `results/asr_<date>.csv`.
- `ocr_f1.py` — field-level F1 for amount, date, vendor, tax ID, IBAN (EN vs AR).
