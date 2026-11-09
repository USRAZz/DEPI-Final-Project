"""Quarantined extractor (SDD §5.1): reads UNTRUSTED documents, has NO tools, returns only ExtractResponse.
Runs in its own container so document content can never reach the Finance Agent."""
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, status
from securefin_contracts import ExtractResponse

from .convert import to_response
from .pipeline import process_invoice

app = FastAPI(title="SecureFin Quarantined Extractor")

ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
MAX_BYTES = 10 * 1024 * 1024


@app.get("/health")
def health():
    return {"service": "extractor", "status": "ok"}


@app.post("/v1/extract", response_model=ExtractResponse)
def extract(file: UploadFile) -> ExtractResponse:
    """OCR -> isolated LLM extraction (masked text) -> checks -> ExtractResponse.
    Anything that does not fit the shared schema comes back as NEEDS-REVIEW with data=None."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"allowed types: {sorted(ALLOWED)}")
    body = file.file.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file larger than 10 MB")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"  # never trust the client's file name
        path.write_bytes(body)
        return to_response(process_invoice(path))
