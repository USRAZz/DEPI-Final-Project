# n8n automations (owner: M4 Ziad)

n8n notifies and reports. It never decides allow / hold / block, never writes approvals and has no database
access. If n8n is down, payments are still held or blocked correctly; only messages and the nightly report stop.

## Try it now (no setup)

```powershell
powershell -ExecutionPolicy Bypass -File n8n\demo.ps1
```

This starts a throwaway n8n on port 5680 with the four workflows published, and prints four links. Each link is
a **Test form**: the fields are already filled in, you press **Run**, and the result appears on the screen.
Nothing is sent or stored, and no `.env`, credential or account is needed.

| Link | What you enter | What you see |
|---|---|---|
| `/form/securefin-test-alert` | which workflow "failed" and an error text | the alert the team would get |
| `/form/securefin-test-intake` | any invoice file from the project, e.g. `tests/fixtures/synthetic/clear_invoices_20/STRESS3-001.pdf` | the "new invoice" message with the file's SHA-256 name (compare with `Get-FileHash`) |
| `/form/securefin-test-notify` | a decision (hold / block / second approval / bank change), a number, reasons | the Arabic + English message for the approver |
| `/form/securefin-test-integrity` | what the check should find (all good / edited row / deleted rows / attack got through) | the scorecard, OK or FAILED |

Remove it with `powershell -ExecutionPolicy Bypass -File n8n\demo.ps1 -Stop`.

In your own n8n: import a file from `workflows/`, open it, choose **Execute workflow** on the "Test form" node,
and the same form opens. The forms use no environment variables, so they also work where n8n blocks env access.
The form path only shows text on the screen: it never sends to Telegram, so it is not a way around the
signature check of workflow 2.

## Standalone now, connected later

The other services are not finished, so every workflow runs on its own today. Nothing in the JSON changes when
you connect one: you fill in its URL in `.env` and restart n8n.

| File in `workflows/` | Standalone (URL empty, the default) | Connected (set in `.env`) |
|---|---|---|
| `0-error-alerts.json` | Any failed run in the other three → Telegram, email if Telegram fails | same, no service needed |
| `1-invoice-email-intake.json` | Invoice email → Telegram "new invoice received" with the sender and the file hash; the same file is announced once. Nothing is stored | `N8N_INVOICE_UPLOAD_URL` + `N8N_INTAKE_TOKEN`: uploads to the api (Karim's endpoint, not built yet) |
| `2-decision-notifications.json` | Send events yourself with `n8n/tools/send_event.py` → Arabic + English Telegram message | the gateway posts the same signed event (Anan, not built yet); no setting changes in n8n |
| `3-nightly-integrity-run.json` | Runs on **simulated** answers; every report starts with "DEMO MODE: simulated data, nothing real was checked" | `N8N_AUDIT_VERIFY_URL` + `AUDIT_VERIFY_TOKEN` (endpoint on branch `feat/gateway/db-store-audit`); `N8N_ATTACK_RUN_URL` when the attack runner exists |

Standalone integrity demo (the alert arrives on Telegram through workflow 0):

```bash
curl -X POST -H "X-Run-Token: <token>" -H "Content-Type: application/json" -d '{"simulate": "broken_chain"}' http://localhost:5678/webhook/securefin/integrity-run
```

`simulate` can be `broken_chain`, `deleted_rows` or `attack_miss`; leave it out for an all-good run. In standalone
mode the outside heartbeat is not pinged, and simulated entry counts are kept apart from real ones.

Tested on `n8nio/n8n:2.46.7` against mock services: all four import, publish and run. Not tested against
a real mailbox (the IMAP trigger was replaced by a webhook in the test), real Telegram, or real SMTP.
Both modes were tested: standalone with no service URL set, connected against the mocks.

## Set up

1. In `.env`: `N8N_ENCRYPTION_KEY` (`openssl rand -hex 32`, never change it afterwards) and the n8n block from
   `.env.example`. n8n refuses to start without the key.
2. `docker compose --profile n8n up -d n8n`, open http://localhost:5678 and create the owner account.
3. Credentials. Copy `credentials.example.json` to `credentials.json` (git-ignored), fill it in, then:

   ```bash
   docker compose cp n8n/credentials.json n8n:/tmp/credentials.json
   docker compose exec n8n n8n import:credentials --input=/tmp/credentials.json
   docker compose exec -u root n8n rm /tmp/credentials.json
   ```

   Importing keeps the ids the workflows refer to. Credentials made by hand in the editor get new ids and must
   be picked again in every node. Use a Gmail **app password** for IMAP and SMTP (an OAuth token can expire
   during the demo).
4. Workflows (repeat after every change to the JSON; importing un-publishes, so publish again):

   ```bash
   docker compose exec n8n sh -c 'n8n import:workflow --separate --input=/workflows && for w in sfErrorAlerts0001 sfInvoiceIntake001 sfDecisionNotify01 sfIntegrityRun001; do n8n publish:workflow --id=$w; done'
   docker compose restart n8n
   ```

   The intake workflow needs the IMAP credential from step 3 before it is published.
5. Check: `python n8n/tools/send_event.py hold --payment 1 --reason TEST` (with `N8N_WEBHOOK_HMAC_SECRET` set in
   your shell) should answer `202` and a Telegram message should arrive.

Edit workflows in the editor, then export them back: `n8n export:workflow --id=<id> --output=/tmp/x.json`.

## Contracts (for connecting later)

### 1. Upload (api, Karim)

`POST /v1/invoices/upload`, multipart: `file`, `source=email`, `sender`, `sha256`.
Headers: `X-Service-Token: $N8N_INTAKE_TOKEN` (a token valid for this endpoint only), `X-Company-Id`,
`Idempotency-Key` (SHA-256 of `Message-ID:file-sha256`).

- `2xx` stored. `409` same file already stored (UNIQUE `source_hash`): n8n treats it as done, not as a failure.
- Anything else is retried (3 tries, 5 s apart: n8n's maximum wait) and then alerted with the file hash.
- The api is the only place that checks the real file type and the size limit (`415`, `413`). n8n keeps
  attachments whose declared MIME type is PDF / PNG / JPEG / WebP / TIFF, at most 5 per email, and names each file
  `<sha256>.<ext>` (Arabic names arrive garbled and are chosen by the sender).
- A failed email is already marked read. The alert carries the hash; upload that file by hand.

### 2. Decision event (gateway, Anan)

`POST $N8N_DECISION_WEBHOOK_URL` after the decision is stored. Fire and forget: 2 s timeout, never wait for it,
never change a decision because of it.

```json
{"event_id": "uuid", "event_type": "hold | block | needs_second_approval | bank_change_pending",
 "company_id": 1, "payment_request_id": 123, "vendor_id": null,
 "reasons": ["VENDOR_ACCOUNT_MISMATCH"], "expires_at": "2026-11-12T10:00:00Z"}
```

Headers: `X-SecureFin-Timestamp: <unix seconds>` and
`X-SecureFin-Signature: sha256=<hex HMAC-SHA256(N8N_WEBHOOK_HMAC_SECRET, "<timestamp>.<raw body>")>`.
`n8n/tools/send_event.py` is a working reference.

- `202` accepted, `401` rejected: bad signature, timestamp more than 5 minutes off, secret shorter than 32
  characters, unknown `event_type`, or a missing id (`vendor_id` for `bank_change_pending`, else
  `payment_request_id`). A repeated `event_id` is accepted and not sent again.
- `N8N_WEBHOOK_HMAC_SECRET` must not be the approval signing key: n8n can read it.
- The message holds ids, the event type, up to 3 reasons (rule codes today; SHAP reasons when the model has
  them) and a link built from `APP_BASE_URL`. No amounts, vendor names or bank details go to Telegram.
- **No approve buttons.** The link opens the app; approval goes through the gateway only.

### 3. Integrity run

`POST $N8N_AUDIT_VERIFY_URL` with `{"company_id": 1}` and `X-Service-Token: $AUDIT_VERIFY_TOKEN` →
`{"ok": true, "entries": 12, "first_broken_id": null, "head_hash": "..."}` (one call per id in
`N8N_AUDIT_COMPANY_IDS`).

`POST $N8N_ATTACK_RUN_URL` with `X-Service-Token: $N8N_EVAL_TOKEN` → `{"total": 22, "blocked": 22, "missed": []}`.
Not built: `eval/run_asr.py` has no `run_case()` yet. Give it its own small service, not the risk service (the
suite attacks the api, the gateway and the database). While the URL is empty the report says
"attack suite ... NOT checked".

The run **fails** (alert through workflow 0) when: a chain is broken; the gateway gives no clear verdict (timeout,
5xx, odd body); the number of audit entries is lower than at the last good run (a hash chain cannot show deleted
newest rows, the count can); any attack got through; the suite ran fewer than `N8N_ATTACK_MIN_CASES` cases.

No OK run for 26 hours → alert (checked every hour, at most one alert a day). That check lives in n8n, so it
cannot see n8n itself being down: set `N8N_HEARTBEAT_URL` to an outside monitor's ping URL for that.

Run it now: `curl -X POST -H "X-Run-Token: <value from credentials.json>" http://localhost:5678/webhook/securefin/integrity-run`
→ `200` with the scorecard, or `500` plus an alert.

## Demo: tampering is caught

The gateway's database role cannot `UPDATE audit_log`, so play the database administrator:

```bash
docker compose exec postgres psql -U securefin -c "UPDATE audit_log SET decision = 'ALLOW' WHERE id = (SELECT max(id) - 1 FROM audit_log)"
```

Then run the integrity check: Telegram shows "hash chain broken at audit_log id N".
For "gateway down = blocked", run `docker compose stop gateway` in a terminal and send a payment. Do not give
n8n the Docker socket for this: that is root on the host.
