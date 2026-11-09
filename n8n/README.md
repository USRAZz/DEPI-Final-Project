# n8n automations (owner: M4 Ziad)

Start: `docker compose --profile n8n up -d n8n`, open http://localhost:5678, then
`docker compose exec n8n n8n import:workflow --input=/workflows/invoice-email-intake.json`.

## invoice-email-intake.json

Unread email in the invoice inbox -> keep PDF/image attachments -> `POST $N8N_INVOICE_UPLOAD_URL`
(multipart field `file`, plus `source=email`, `sender`) -> fail the run on any non-2xx answer.

- Create an IMAP credential named **Invoice inbox (IMAP)** in the n8n UI (never commit mailbox passwords).
- Headers: `X-Service-Token: $INTERNAL_SERVICE_TOKEN`, `X-Company-Id: $N8N_COMPANY_ID`.
- The workflow is imported **inactive**; activate it after the API endpoint exists.

**Needs Karim:** the API has no upload endpoint yet. Expected contract: `POST /v1/invoices/upload`,
service-to-service auth with `INTERNAL_SERVICE_TOKEN` (the same token the risk service uses for
`/risk-features`), returns 201 with the invoice id; 409 for the same file twice (UNIQUE source_hash), 413/415
from the extractor limits. Change `N8N_INVOICE_UPLOAD_URL` if the path differs.

Image pinned to `n8nio/n8n:2.46.7` in the root `docker-compose.yml`; import tested on that version.
