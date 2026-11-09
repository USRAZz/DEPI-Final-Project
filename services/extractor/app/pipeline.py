"""Invoice pipeline (prompt chaining):
OCR -> LLM 1 (raw text -> fields) -> GATE 1 (checks) -> LLM 2 (category) -> GATE 2 (duplicate) -> result.
Saving to the database is the API's job; this returns a clear result object."""
import json
import os
import re
import time
from pathlib import Path

from ai_core.llm import Budget, BudgetExceeded, StructuredOutputError, get_llm
from ai_core.prompts import load_prompt, untrusted

from .ocr import extract_text
from .schemas import CATEGORIES, CategoryResult, ExtractionResult, InvoiceFields

_SEEN: dict[str, str] = {}  # in-memory duplicate memory for local tests; Ziad's risk service replaces it


def _iban_ok(iban: str) -> bool:
    s = iban.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


def check_fields(f: InvoiceFields) -> list[str]:
    """GATE 1: business sanity checks on the extracted fields."""
    issues = []
    tol = max(1.0, abs(f.total_amount) * 0.005)
    if f.total_amount <= 0:
        issues.append("total is not positive")
    if f.subtotal is not None and f.tax_amount is not None and abs(f.subtotal + f.tax_amount - f.total_amount) > tol:
        issues.append("subtotal + tax does not equal total")
    items = [i.total for i in f.line_items if i.total is not None]
    if items and f.subtotal is not None and abs(sum(items) - f.subtotal) > tol:
        issues.append("line items do not add up to subtotal")
    if f.invoice_date and f.due_date and f.due_date < f.invoice_date:
        issues.append("due date is before invoice date")
    if f.iban and not _iban_ok(f.iban):
        issues.append("IBAN checksum is invalid")
    return issues


def _dup_key(f: InvoiceFields) -> str:
    vendor = re.sub(r"\W+", "", f.vendor_name.lower())
    return f"{vendor}|{f.invoice_number.lower()}|{f.total_amount:.2f}"


def process_invoice(path, *, invoice_id: str | None = None, llm_extract=None, llm_categorize=None,
                    seen: dict | None = None) -> ExtractionResult:
    seen = _SEEN if seen is None else seen
    budget = Budget(max_tokens=int(os.getenv("INVOICE_MAX_TOKENS", "12000")),
                    max_seconds=float(os.getenv("INVOICE_MAX_SECONDS", "90")))

    def result(status, **kw):
        return ExtractionResult(status=status, usage={"tokens": budget.tokens},
                                seconds=round(time.perf_counter() - budget.started, 2), **kw)

    # 1) OCR: plain code
    try:
        text = extract_text(path)
    except Exception as e:
        return result("FAILED", issues=[f"OCR failed: {e}"])
    if len(text.strip()) < 20:
        return result("FAILED", issues=["OCR returned almost no text"], ocr_chars=len(text))

    # 2) LLM 1: the ONLY step that sees the raw text. No tools; JSON only.
    llm_extract = llm_extract or get_llm("extractor")
    system = load_prompt("extractor", json_schema=json.dumps(InvoiceFields.model_json_schema(), ensure_ascii=False))
    try:
        fields = llm_extract.structured([{"role": "system", "content": system},
                                         {"role": "user", "content": untrusted(text)}],
                                        InvoiceFields, budget=budget)
    except (StructuredOutputError, BudgetExceeded) as e:
        return result("FAILED", issues=[f"extraction failed: {e}"], ocr_chars=len(text))

    # 3) GATE 1: checks in code
    issues = check_fields(fields)

    # 4) LLM 2: sees only the validated fields, never the raw text
    llm_categorize = llm_categorize or get_llm("categorizer")
    summary = {"vendor_name": fields.vendor_name, "total_amount": fields.total_amount, "currency": fields.currency,
               "items": [i.description for i in fields.line_items][:20]}
    system = load_prompt("categorize", categories=", ".join(CATEGORIES),
                         json_schema=json.dumps(CategoryResult.model_json_schema(), ensure_ascii=False))
    try:
        category = llm_categorize.structured([{"role": "system", "content": system},
                                              {"role": "user", "content": untrusted(json.dumps(summary, ensure_ascii=False))}],
                                             CategoryResult, budget=budget)
        if category.confidence < 0.5:
            issues.append("low-confidence category")
    except (StructuredOutputError, BudgetExceeded) as e:
        category = None
        issues.append(f"categorization failed: {e}")

    # 5) GATE 2: duplicate check
    key = _dup_key(fields)
    dup = seen.get(key)
    if dup:
        issues.append(f"possible duplicate of {dup}")
    else:
        seen[key] = invoice_id or Path(path).name

    return result("FLAGGED" if issues else "READY", fields=fields, category=category, issues=issues,
                  duplicate_of=dup, ocr_chars=len(text))