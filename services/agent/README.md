# services/agent — AI Agent & Quarantined Extractor

**Owner:** M2 (Yossra) · **Local port:** 8001

**Owns (only this service writes):** LangGraph finance agent, tool wrappers (call api with the user's JWT), risk explainer, report writer

**Endpoints:** `/v1/chat`, `/v1/explain`

## Run alone
```bash
cd services/agent
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ../../contracts -r requirements-dev.txt
uvicorn app.main:app --reload --port 8001
pytest
```

## Rules
- Import shared types from `securefin_contracts` — never redefine them here.
- Need data owned by another service? Call its endpoint; do not write its tables.
- Document every new endpoint in this README.

Prompts live in the repo-root `prompts/` folder (SDD §6). The extractor is a separate service: `services/extractor`.
