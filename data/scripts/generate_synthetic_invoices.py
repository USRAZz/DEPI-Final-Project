"""Generate a reproducible, fully synthetic SecureFin invoice OCR fixture set.

Requires Windows PowerShell 5.1 and Pillow.
The output PDFs are image-only so they can be used for OCR evaluation.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "fixtures" / "synthetic" / "invoices"
MANIFEST = ROOT / "tests" / "fixtures" / "synthetic" / "manifest.json"
VENDORS = [
    ("شركة النيل للتوريدات", "Nile Supply Co."),
    ("مؤسسة الأفق المكتبي", "Horizon Office Supplies"),
    ("الرواد للأجهزة", "Pioneers Equipment"),
    ("شركة دلتا للخدمات", "Delta Services"),
    ("المستقبل للتقنية", "FutureTech Solutions"),
    ("مصنع اليسر للتعبئة", "Yosr Packaging Factory"),
    ("مكتبة الصفوة", "Safwa Stationery"),
    ("النور للصيانة", "Al Nour Maintenance"),
    ("شركة جسور للنقل", "Jusoor Transport"),
    ("الشرق للضيافة", "East Hospitality"),
]
AR_ITEMS = ["أدوات مكتبية", "خدمات صيانة", "أجهزة شبكات", "مواد تعبئة", "خدمات نقل"]
EN_ITEMS = ["Office supplies", "Maintenance service", "Network equipment", "Packaging material", "Transport service"]


def records() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    duplicate_pairs = {5: 4, 7: 6, 22: 21, 37: 36}
    high_value_indices = {12, 13, 28, 29, 42, 43}
    bank_mismatch_indices = {17, 18, 31, 32, 46, 47}
    for i in range(50):
        vendor_index = i % len(VENDORS)
        ar_name, en_name = VENDORS[vendor_index]
        language = "ar" if i < 20 else "en" if i < 35 else "mixed"
        subtotal = 1250 + ((i * 137) % 9200)
        expected = "normal"
        duplicate_of = None
        invoice_number = f"SF-{1001 + i:04d}"
        duplicate_original = result[duplicate_pairs[i]] if i in duplicate_pairs else None
        if duplicate_original:
            vendor_index = int(duplicate_original["vendor_index"])
            ar_name, en_name = VENDORS[vendor_index]
            subtotal = int(duplicate_original["subtotal_egp"])
            invoice_number = str(duplicate_original["invoice_number"])
            duplicate_of = str(duplicate_original["id"])
            expected = "duplicate"
        if i in high_value_indices:
            subtotal = 102000 + (i % 6) * 1150
            expected = "high_value_review"
        tax = round(subtotal * 0.14, 2)
        total = round(subtotal + tax, 2)
        inv_date = date.fromisoformat(str(duplicate_original["invoice_date"])) if duplicate_original else date(2026, 1, 5) + timedelta(days=i * 3)
        normal_iban = f"EG00TEST{vendor_index + 1:02d}{(vendor_index + 1) * 123456789:09d}"
        invoice_iban = normal_iban
        master_iban = normal_iban
        if i in bank_mismatch_indices:
            invoice_iban = f"EG00TEST99{(i + 1) * 987654321:09d}"
            expected = "bank_account_mismatch_review"
        result.append({
            "id": f"INV-{i + 1:03d}",
            "file": f"INV-{i + 1:03d}.pdf",
            "language": language,
            "layout_variant": i % 5,
            "vendor_index": vendor_index,
            "vendor_name_ar": ar_name,
            "vendor_name_en": en_name,
            "invoice_number": invoice_number,
            "invoice_date": inv_date.isoformat(),
            "currency": "EGP",
            "subtotal_egp": subtotal,
            "tax_rate": 0.14,
            "tax_egp": tax,
            "total_egp": total,
            "tax_id": f"SYNTH-TAX-{vendor_index + 1:04d}",
            "invoice_iban": invoice_iban,
            "vendor_master_iban": master_iban,
            "expected_label": expected,
            "duplicate_of": duplicate_of,
            "data_notice": "Synthetic test data; not valid for payment or tax filing.",
        })
    return result


def main() -> None:
    powershell = shutil.which("powershell")
    if not powershell:
        raise SystemExit("This generator currently requires Windows PowerShell 5.1.")
    OUT.mkdir(parents=True, exist_ok=True)
    work_dir = ROOT / ".tmp-synthetic-invoices"
    work_dir.mkdir(exist_ok=True)
    items = records()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "dataset": "SecureFin Synthetic Invoice OCR Set",
        "version": "1.0",
        "count": len(items),
        "synthetic_only": True,
        "license": "CC0-1.0",
        "fields": ["vendor_name_ar", "vendor_name_en", "invoice_number", "invoice_date", "tax_id", "invoice_iban", "subtotal_egp", "tax_egp", "total_egp"],
        "records": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="securefin-invoices-", dir=work_dir) as temp_name:
        temp = Path(temp_name)
        subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "data" / "scripts" / "render_synthetic_invoices.ps1"), "-Manifest", str(MANIFEST), "-OutputDirectory", str(temp)], check=True)
        pages = sorted(temp.glob("INV-*.png"))
        if len(pages) != 50:
            raise RuntimeError(f"Expected 50 rendered pages; got {len(pages)}")
        for row in items:
            page = temp / (Path(str(row["file"])).stem + ".png")
            with Image.open(page) as image:
                image.convert("RGB").save(OUT / str(row["file"]), "PDF", resolution=120)
    print(f"Created {len(items)} image-only PDF invoices in {OUT}")
    print(f"Ground truth: {MANIFEST}")


if __name__ == "__main__":
    main()
