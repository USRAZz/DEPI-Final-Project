"""Mask bank and personal data before any text reaches the LLM provider.

Decision (SecureFin plan 1.2): OpenAI is the LLM provider, so IBANs, tax registration numbers, phone
numbers and e-mail addresses are replaced with placeholders before every call. Values the pipeline needs
(IBAN, tax id) are read from the OCR text by code instead, with find_ibans / find_tax_ids.
"""
import re

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# IBAN: 2 letters + 2 check digits, then either 10-30 alphanumerics written together, or groups of 4
# separated by single spaces (the printed form) with a shorter last group.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[A-Z0-9]{10,30}|(?: [A-Z0-9]{4}){2,7}(?: [A-Z0-9]{1,4})?)\b")
# Words that label an IBAN on an invoice (English / Arabic).
_IBAN_LABEL = re.compile(r"(?i)iban|[اأآإ]يبان|رقم الحساب")
# Egyptian tax registration number: 9 digits (often 3-3-3), only when a tax label is close before it.
_TAX = re.compile(r"(?i)(tax|t\.?r\.?n|vat|ضريب|التسجيل الضريبي|رقم التسجيل)[^\d\n]{0,30}(\d{3}[-\s]?\d{3}[-\s]?\d{3})\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Egyptian mobile (01x + 8 digits) and +20 numbers.
_PHONE = re.compile(r"(?<!\d)(?:\+?20[\s-]?)?0?1[0125](?:[\s-]?\d){8}(?!\d)")


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


def _iban_valid(candidate: str) -> bool:
    s = candidate.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


def find_ibans(text: str) -> list[str]:
    """IBANs, spaces removed, in reading order: valid checksums first, then invalid ones.

    An IBAN whose checksum fails is kept only when an IBAN label is just before it, so the pipeline can
    flag it (IBAN_CHECKSUM_INVALID) instead of dropping it; other IBAN-shaped codes (order refs) are ignored.
    Only trailing groups with a letter are dropped (a following word taken as a group). Digit groups are
    never dropped: a shorter number passes the mod-97 check by chance about 1 time in 97.
    """
    s = normalize_digits(text).upper()
    valid, invalid = [], []
    for m in _IBAN.finditer(s):
        groups = m.group(0).split(" ")
        while len(groups) > 1 and not _iban_valid("".join(groups)) and re.search(r"[A-Z]", groups[-1]):
            groups.pop()
        iban = "".join(groups)
        if len(iban) < 15:
            continue
        if _iban_valid(iban):
            valid.append(iban)
        elif _IBAN_LABEL.search(s[max(0, m.start() - 40):m.start()]):
            invalid.append(iban)
    return list(dict.fromkeys(valid + invalid))


def find_tax_ids(text: str) -> list[str]:
    return list(dict.fromkeys(re.sub(r"\D", "", m.group(2)) for m in _TAX.finditer(normalize_digits(text))))


def mask_sensitive(text: str) -> str:
    """Replace bank and personal data with placeholders. Digits are normalised to Latin first."""
    s = normalize_digits(text)
    s = _IBAN.sub(lambda m: "[IBAN]" if len(m.group(0).replace(" ", "")) >= 15 else m.group(0), s)
    s = _TAX.sub(lambda m: m.group(0)[: m.start(2) - m.start(0)] + "[TAX_ID]", s)
    s = _EMAIL.sub("[EMAIL]", s)
    return _PHONE.sub("[PHONE]", s)


def mask_messages(messages: list[dict]) -> list[dict]:
    """Copy of chat messages with every text part masked (images are left as they are)."""
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            content = mask_sensitive(content)
        elif isinstance(content, list):
            content = [{**p, "text": mask_sensitive(p["text"])} if p.get("type") == "text" else p for p in content]
        out.append({**m, "content": content})
    return out
