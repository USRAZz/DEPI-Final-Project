# SecureFin AI

Expense and supplier-payment software for small and mid-size companies in Egypt. It reads invoices in Arabic and
English, an assistant answers questions and prepares payments, and every payment passes a security gateway
(permissions, policy, risk, maker-checker, signed approvals) and lands in a tamper-evident audit log.

**The assistant proposes, the gateway decides, the api executes.** No AI component can pay, approve or delete.

## Services

| Folder | What it does | Owner | Port (local) |
|---|---|---|---|
| `services/api` | companies, users, invoices, vendors, payment requests, approvals and execution through the gateway; the screens' backend; forwards chat and reports to the agent | Karim | 8000 |
| `services/agent` | assistant: router, read-only agent loop, alerts with reasons, reports (orchestrator-workers + evaluator), risk explanations | Yousra | 8001 (this machine only) |
| `services/gateway` | allow / hold / block, approvals with HMAC signatures, execute-check, audit hash chain | Anan | 8002 (this machine only) |
| `services/risk` | rule-based risk score with reason codes | Ziad | 8003 |
| `services/extractor` | quarantined invoice reader: OCR → LLM fields → checks (incl. hidden-instruction guard) | Yousra | 8004 |
| `frontend` | React app, Arabic (RTL) and English | Karim + page owners | 5173 |
| `contracts` | the shared data shapes (Pydantic); every service imports them | all four | – |
| `n8n` | e-mail intake, notifications, nightly audit check | Ziad | 5678 |

Flow of one invoice: upload → extractor → api stores it → risk scores it → assistant proposes a payment → gateway
decides → approvers sign → api executes after the gateway's execute-check → audit log.

## Run

```powershell
Copy-Item .env.example .env      # then fill in the keys and change every change-me value
docker compose up --build
```

Secrets each service needs: `INTERNAL_SERVICE_TOKEN` (risk and gateway → api), `GATEWAY_SERVICE_TOKEN`
(api → gateway), `AGENT_SERVICE_TOKEN` (api → agent), `APPROVAL_HMAC_KEY` (32+ characters, gateway),
`AUDIT_VERIFY_TOKEN` (n8n → gateway), and an LLM key (`OPENROUTER_API_KEY` with `LLM_PROVIDER=openrouter`).
Without them the services stay closed (503) rather than run unprotected.

## Test

```powershell
make test        # contracts + every service
make test-ai     # the AI part across services (offline, fake LLMs)
make lint
```

CI (`.github/workflows/ci.yml`) runs all of these on every pull request, plus the migrations on PostgreSQL and the
frontend build.

## AI part (Yousra)

- Prompts: `prompts/*_v1.md`, loaded by `ai_core/prompts.py`. Every outside text is wrapped as untrusted data.
- Privacy: IBANs, tax ids, phones and e-mails are masked before any LLM call (`ai_core/privacy.py`).
- Free tiers only: `LLM_FALLBACK_PROVIDERS=openrouter,groq,groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,openai`. When one answers 429
  (free quota used up) the next one answers; it is used again by itself when its quota renews (the reset time the
  provider sends). Check with `python -m ai_core.llm_check` (`--call` for one tiny request each).
- Model choice: one fixed model per role, or `LLM_ROUTING=jev` so OpenRouter's Jev Router picks the model per
  request (`ai_core/llm.py`). Check it with `python -m ai_core.jev_check` (`--call` for one tiny test request).
- Evaluation with the real LLM: `python eval/ai_eval/run_ai_eval.py` (`eval/ai_eval/README.md`). Run it after
  changing a prompt. Attack cases: `eval/attack_suite/`.
- Try it locally: `python -m ai_core.try_ai chat` (or `ask`, `report`, `extract`, `route`, `ocr`).
- On a machine where an antivirus or proxy inspects HTTPS, set `USE_SYSTEM_CERTS=true` (`pip install truststore`).

## Work rules

Branch from `dev` (`feat/<area>/<task>`), small pull requests, the owner of each folder reviews; `contracts/`
changes need all four. No secrets or real data in Git. Plan: `team_work.txt`, history: `team_log.txt`.
