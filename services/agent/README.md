# services/agent — AI Agent

**Owner:** M2 (Yossra) · **Local port:** 8001

**Owns (only this service writes):** finance agent loop, read-only tool wrappers (call the api with the user's own
identity), risk explainer. The invoice reader is a separate service: `services/extractor`.

**Endpoints:** `/v1/chat`, `/v1/reports`, `/v1/explain`

## `POST /v1/chat` (`ChatRequest` → `ChatResponse`)
Router (one small LLM call) → one of: clarifying question · upload hint · report (below, answer = its Markdown) ·
agent loop (plan → one read-only tool → observe, at most `LLM_MAX_STEPS`, with token/time budgets) → checked proposals.

- **Never executes.** The only output that can lead to a payment is a `ProposedAction(create_payment_request)` with
  exactly `invoice_id, vendor_id, amount, currency`; the api sends it to the gateway.
- **Proposals only for payment requests.** If the router did not classify the user's message as `payment_request`,
  any proposal the model makes is dropped and the user is told (a pasted e-mail asking to pay, attack ATK-006).
- **Chat memory.** `history` (≤ 20 turns, the last 10 are used, 1,000 characters each) is passed to the agent as ONE
  tagged data message — a client could forge an "assistant" turn, so it is never treated as a real one. The router
  sees the last exchange, so "yes, pay it" works; the language is still detected from the new message.
- Headers: `Authorization: Bearer <user JWT>` (when the api has JWT), `X-User-Id` (the api's current dev login),
  `X-User-Role`. The tools forward the user's identity, never a service account.
- `mode: "dry_run"` returns the answer without proposals.
- **Alerts always come with their reason** (`app/alerts.py`). Every flagged or risky invoice the tools returned in
  this turn is in `alerts` with `reasons` (risk rules + invoice-reader issues, in plain words, in the user's
  language) and is listed under the answer ("Why these invoices have alerts:" / "سبب التنبيهات:"). Built by code
  from the data, so it is there even when the model forgets; a flagged invoice the model did not score is scored here.
- `sources`: the read-only tools the answer is based on. The UI page is `frontend/src/features/agent-chat`.

## `POST /v1/reports` (`ReportRequest` → `Report`) — pattern ④, `app/reports.py`
Orchestrator-workers + evaluator-optimizer, as in the flowchart:

1. **Orchestrator** (LLM, `report_orchestrator_v1`) reads the request and picks the sections and the period from a
   fixed catalogue: `spending_summary, top_vendors, categories, anomalies, unpaid_invoices, trend`. Unknown
   sections are dropped; an invalid or future period is corrected (and the `notes` say so).
2. **Facts** (code): each section's numbers from the same read-only tools as the chat, with the user's identity.
3. **Workers** (LLM, `report_worker_v1`, in parallel): one section each, from its own facts only.
4. **Synthesizer** (LLM, `report_writer_v1`): title + summary → draft.
5. **Evaluator**: code first — every number in the draft must exist in the facts, every section in order, the
   user's script — then the LLM (`report_evaluator_v1`): clear, complete, consistent?
6. **Optimizer** (`report_writer_v1` with the feedback), at most 3 evaluation rounds.

`quality`: `passed` (numbers checked + evaluator OK) · `numbers_checked` (numbers OK, evaluator feedback in `notes`)
· `fallback` (no draft matched the data, or a limit/provider failure: the sections are fixed wording built from the
facts). **A number the model invented never reaches the user.** `markdown` is the whole report for the dashboard and
the PDF export; `models` lists which model answered each call.

## Model choice with Jev Router
`LLM_ROUTING=jev` sends every role's call to OpenRouter's `typesafe/jev-router`, which picks the model per request.
Each role sends a cost tier (`low` for routing, labels and report planning; `medium` for the agent, the extractor and
the report writer; `high` for the report evaluator), changeable with `<ROLE>_JEV_COST_TIER`. Narrow the pool with
`JEV_MODELS` / `JEV_EXCLUDED_MODELS`. A role with its own `<ROLE>_MODEL` keeps it. If the router answers 404/503,
the call is retried once on `JEV_FALLBACK_MODEL` (default `OPENROUTER_MODEL`), and for `JEV_RETRY_SECONDS`
(300) the next calls go straight to the fallback. The chosen model is in `LLM.usage.models` and in `Report.models`.
Masking (`ai_core/privacy.py`) happens before Jev sees anything.

**Is Jev usable with our key?** `python -m ai_core.jev_check` (free: settings per role, catalogue, key and credit)
and `python -m ai_core.jev_check --call` (one tiny request; prints the model Jev picked, or the exact reason for a
401/402/403/404/503 and what to do). OpenRouter serves Jev only in the global data region and in workspaces that
allow it; a 404 means the key's workspace does not, or the pool limits leave no model. On a machine where an
antivirus or proxy inspects HTTPS, set `USE_SYSTEM_CERTS=true` (`pip install truststore`).

## `POST /v1/explain` (`ExplainRequest` → `RiskExplanation`)
A `RiskScore`'s rule codes in plain words, Arabic or English (prompt `prompts/risk_explain_v1.md`). Every code the
risk service emits has fixed wording in `app/explain.py` (`source: "template"`). With `EXPLAIN_USE_LLM=true` the model
may reword it (`source: "llm"`), but only a reply that covers exactly the same codes in the same order, in the right
script, is used; anything else falls back to the templates. It explains; it never changes a decision.
When the risk service adds a rule code, add its wording to `MEANINGS` (a test fails until you do).

## Run alone
```bash
cd services/agent
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ../../contracts -r requirements-dev.txt
uvicorn app.main:app --reload --port 8001
pytest
```

## Evaluate after changing a prompt
`python eval/ai_eval/run_ai_eval.py` from the repo root (needs an LLM key). See `eval/ai_eval/README.md`.

## Rules
- Import shared types from `securefin_contracts` — never redefine them here.
- Need data owned by another service? Call its endpoint; do not write its tables.
- Document every new endpoint in this README.

Prompts live in the repo-root `prompts/` folder (SDD §6).

## Waiting on the api (Karim)
`BACKEND=api` needs list endpoints the api does not have yet: `GET /invoices` (filters), `GET /transactions`
(date range) and a per-invoice risk read. Until then the agent runs on `BACKEND=mock`. The paths are in
`ApiBackend.PATHS` (`app/tools.py`).
