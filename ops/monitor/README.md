# Monitoring (owner: M4 Ziad)

Three layers, from cheapest to most complete. None of them can change a payment decision: if monitoring is down,
payments are still held or blocked correctly; only the warning is missing.

| Layer | Where | What it catches | Who is told |
|-------|-------|-----------------|-------------|
| Container healthchecks | every `services/*/compose.yaml`, postgres in `docker-compose.yml` | a service that runs but no longer answers `GET /health` | `docker compose ps` shows `unhealthy`; `api` and `gateway` do not start until what they need is healthy |
| Health watch (n8n workflow 4) | `n8n/workflows/4-health-watch.json` | a service down or answering anything but `{"status": "ok"}`, checked every 5 min | Telegram (email if Telegram fails) through workflow 0, when it goes down and every hour while it stays down |
| Nightly integrity run (n8n workflow 3) | `n8n/workflows/3-nightly-integrity-run.json` | an edited or deleted audit row, an attack that got through, or the nightly run itself not happening (26 h dead man's switch) | the same alert path |

Plus the monthly backup drill (`ops/README.md`), which fails CI if a backup no longer restores.

## Check by hand

```bash
python ops/monitor/check_health.py                         # the compose stack on this machine
AUDIT_VERIFY_TOKEN=... python ops/monitor/check_health.py --audit-companies 1,2
python ops/monitor/check_health.py --base staging-host --json
```

One line per check, `ALL OK` and exit 0, or `SOMETHING IS DOWN` and exit 1. Standard library only, so it runs on
any machine with Python 3.10+. The token is read from the environment and never printed.

## Turn the watch on

In `.env`, set `N8N_HEALTH_URLS` (the compose value is in `.env.example`), then re-import and publish the
workflows (`n8n/README.md`, Set up step 4). It is empty by default, so the n8n-only demo does not report the
services it is not running as down.

## Alert rules

- **Down**: no answer within 5 s, any status but 200, or a body whose `status` is not `ok`.
- One message when a service goes down, then a reminder at most once an hour while anything stays down.
  No message on recovery: the next alert, or the n8n execution list, shows it.
- A failed alert is not lost silently: workflow 0 falls back from Telegram to email.

Verified: `check_health.py` against all five services started locally (uvicorn), with a correct, wrong and
missing audit token (`tests/test_check_health.py` covers down, HTTP 503, wrong status and a broken chain).
Workflow 4 on n8n 2.46.7 (npm install, Node 24) against two live services and one that was down: the scheduled
run failed with `DOWN  ghost: connect ECONNREFUSED`, workflow 0 started; the next runs said `STILL DOWN` without a
new alert; after the service came back the run said `RECOVERED` and cleared the state. The test form showed the
simulated alert.
Not verified here: the containers' healthchecks inside Docker (images could not be pulled in the build
environment), and live Telegram/email delivery.
