# services/extractor — Quarantined Extractor

**Owner:** M2 (Yossra) · **Local port:** 8004

Reads untrusted invoices (PDF/image), runs OCR, and asks an isolated LLM (no tools) for the fixed `InvoiceData` schema.
Anything outside the schema fails validation (`extra="forbid"`) → status NEEDS-REVIEW. The agent never sees raw text.

**Endpoints:** `POST /v1/extract` (file → `InvoiceData`), `GET /health`
**Prompt:** `prompts/extractor_v4.md` (P-02; default since v2 to v4 fixed vendor names and two-language item lines, `PROMPT_VERSION_EXTRACTOR=v1` pins the old one)

Run alone: `pip install -e ../../contracts -r requirements-dev.txt && uvicorn app.main:app --reload --port 8004 && pytest`
