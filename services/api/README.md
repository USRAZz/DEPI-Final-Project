# services/api — Platform & Integration API

**Owner:** M1 (Karim) · **Local port:** 8000

**Owns (only this service writes):** users, roles, role_tools, vendors, invoices, transactions, payment_requests, Alembic migrations, JWT auth, rate limiting, simulated payment executor

**Endpoints:** `/auth/login`, `/invoices/upload`, `/invoices`, `/chat` (proxy to agent), `/payments`, `/reports`

## Run alone
```bash
cd services/api
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ../../contracts -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
pytest
```

## Rules
- Import shared types from `securefin_contracts` — never redefine them here.
- Need data owned by another service? Call its endpoint; do not write its tables.
- Document every new endpoint in this README.
