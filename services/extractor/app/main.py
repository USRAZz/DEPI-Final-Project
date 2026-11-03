"""Quarantined extractor (SDD §5.1): reads UNTRUSTED documents, has NO tools, returns only InvoiceData JSON.
Runs in its own container so document content can never reach the Finance Agent."""
from datetime import date
from decimal import Decimal

from fastapi import FastAPI, UploadFile
from securefin_contracts import InvoiceData

app = FastAPI(title="SecureFin Quarantined Extractor")


@app.get("/health")
def health():
    return {"service": "extractor", "status": "ok"}


@app.post("/v1/extract", response_model=InvoiceData)
async def extract(file: UploadFile):
    """STUB. Real version: OCR (PaddleOCR/Tesseract) -> isolated LLM call with prompts/extractor_v1.md ->
    InvoiceData.model_validate_json(); any validation error -> NEEDS-REVIEW (text outside the schema is dropped)."""
    return InvoiceData(vendor="Stub Vendor", invoice_no="INV-STUB-1", date=date(2026, 10, 1), amount=Decimal("1500"))
