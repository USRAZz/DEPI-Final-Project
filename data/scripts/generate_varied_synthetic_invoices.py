"""Generate a separate 30-invoice OCR stress set with varied layouts and scan quality."""

from __future__ import annotations

import json
import argparse
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[2]
VENDORS = [
    ("شركة السنبلة للتجارة", "Sunbulah Trading"),
    ("مؤسسة جسر الأعمال", "Business Bridge Est."),
    ("المدينة للصناعات", "Al Madina Industries"),
    ("شركة المشرق للتوريد", "Mashreq Supply Co."),
    ("رواد الحلول المكتبية", "Pioneers Office Solutions"),
    ("النخبة للخدمات الفنية", "Elite Technical Services"),
    ("شركة الواحة للنقل", "Oasis Transport"),
    ("المتحدة للأدوات", "United Tools"),
    ("مصنع الكنانة", "Kinana Factory"),
    ("مركز الصفوة التجاري", "Safwa Commercial Center"),
    ("شركة المدار للمقاولات", "Madar Contracting Co."),
    ("الأمان للتجهيزات", "Aman Equipment"),
    ("مصنع النخيل للأغذية", "Palm Food Factory"),
    ("المصرية للتوريدات", "Egyptian Supplies"),
    ("شركة مدارك للتدريب", "Madarik Training"),
    ("أطلس للخدمات اللوجستية", "Atlas Logistics"),
    ("مؤسسة بداية للطباعة", "Bedaya Printing Est."),
    ("شركة الميناء للصيانة", "El Mina Maintenance"),
    ("دلتا للأنظمة الذكية", "Delta Smart Systems"),
    ("بيت الخبرة للاستشارات", "Expert House Consulting"),
    ("شركة النور للمستلزمات", "Al Nour Supplies"),
    ("المصرية لخدمات الأعمال", "Egyptian Business Services"),
    ("المنارة للتجهيزات", "Al Manara Equipment"),
    ("شركة آفاق للطباعة", "Afaq Printing Co."),
    ("مركز الإتقان للصيانة", "Etqan Maintenance Center"),
    ("الوادي للتوزيع", "Al Wadi Distribution"),
    ("مصنع الروابي", "Rawabi Factory"),
    ("المحور للحلول الرقمية", "Mehwar Digital Solutions"),
    ("شركة المرسى للخدمات", "Al Marsa Services"),
    ("أركان للتوريدات", "Arkan Trading"),
]
ITEMS = [
    ("ورق تصوير A4", "A4 copier paper", 175),
    ("حبر طابعة", "Printer toner", 640),
    ("قطع غيار", "Replacement parts", 920),
    ("مياه شرب (عبوات)", "Bottled drinking water", 85),
    ("خدمة صيانة", "Maintenance service", 1250),
    ("خدمات نقل", "Transport service", 780),
    ("معدات شبكات", "Network equipment", 2400),
    ("مواد تعبئة", "Packaging materials", 315),
    ("أدوات مكتبية", "Office supplies", 230),
    ("خدمات استشارية", "Consulting services", 1800),
    ("أحبار وأدوات طباعة", "Ink and printing supplies", 520),
    ("خدمة تركيب", "Installation service", 1450),
    ("معدات سلامة", "Safety equipment", 390),
    ("مواد تنظيف", "Cleaning materials", 110),
    ("اشتراك برمجي", "Software subscription", 2100),
    ("خدمة توصيل", "Delivery service", 260),
    ("قطع كهربائية", "Electrical components", 730),
    ("مستلزمات تغليف", "Wrapping supplies", 185),
    ("تدريب فني", "Technical training", 2300),
    ("خدمة معايرة", "Calibration service", 980),
    ("أجهزة مكتبية", "Office equipment", 1650),
    ("خدمة دعم فني", "Technical support", 890),
    ("مستلزمات كهربائية", "Electrical supplies", 420),
    ("صيانة دورية", "Scheduled maintenance", 1350),
    ("مواد خام", "Raw materials", 275),
    ("خدمات شحن", "Shipping services", 1140),
    ("تراخيص برامج", "Software licenses", 1950),
    ("مستلزمات مكتبية", "Stationery items", 195),
    ("خدمة تركيب أجهزة", "Equipment installation", 1750),
    ("معدات وقاية", "Protective equipment", 360),
]
QUALITY = ["clean", "moderate", "hard"]


def build_records(batch: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    count = 20 if batch == 3 else 30
    clear_languages = ["ar", "en", "mixed"] * 6 + ["ar", "en"]
    for i in range(count):
        if batch == 3:
            language = clear_languages[i]
            language_index = {"ar": 0, "en": 1, "mixed": 2}[language]
            layout = i % 10
            quality = "clean"
            vendor_index = ((i * 3 + layout) % 10) + 20
        else:
            language_index = i % 3
            language = ["ar", "en", "mixed"][language_index]
            layout = i // 3
            quality = QUALITY[(layout + language_index) % 3]
            vendor_index = ((i * 3 + layout) % 10) + ((batch - 1) * 10)
        vendor_ar, vendor_en = VENDORS[vendor_index]
        if batch == 3:
            item_count = 2 + ((i // 2) % 4)
        else:
            item_count = 1 if (layout * 2 + language_index) % 3 == 0 else 2 + ((layout + language_index) % 4)
        line_items: list[dict[str, object]] = []
        subtotal = 0
        for j in range(item_count):
            item_index = ((i + j * 3 + layout) % 10) + ((batch - 1) * 10)
            name_ar, name_en, unit_price = ITEMS[item_index]
            quantity = 1 + ((i + j + layout) % 8)
            total = quantity * unit_price
            subtotal += total
            line_items.append({
                "description_ar": name_ar,
                "description_en": name_en,
                "quantity": quantity,
                "unit_price_egp": unit_price,
                "line_total_egp": total,
            })
        tax = round(subtotal * 0.14, 2)
        month = 2 if batch == 1 else 5 if batch == 2 else 8
        inv_date = date(2026, month, 1) + timedelta(days=i * 2)
        prefix = "STRESS" if batch == 1 else f"STRESS{batch}"
        rows.append({
            "id": f"{prefix}-{i + 1:03d}",
            "file": f"{prefix}-{i + 1:03d}.pdf",
            "language": language,
            "layout_variant": layout,
            "quality_tier": quality,
            "simulated_rotation_degrees": round(((-1) ** i) * (0.15 + (i % 5) * 0.27), 2) if quality != "clean" else 0,
            "vendor_name_ar": vendor_ar,
            "vendor_name_en": vendor_en,
            "invoice_number": f"SYN{batch}-{2026000 + i + 1}",
            "invoice_date": inv_date.isoformat(),
            "purchase_order": f"PO-{batch}{42000 + i}",
            "tax_id": f"SYNTH-REG-{(vendor_index + 1) * 873:06d}",
            "currency": "EGP",
            "line_items": line_items,
            "subtotal_egp": subtotal,
            "tax_rate": 0.14,
            "tax_egp": tax,
            "total_egp": round(subtotal + tax, 2),
            "invoice_iban": f"EG00TEST{vendor_index + 1:02d}{(vendor_index + 7) * 71234567:010d}",
            "synthetic_only": True,
        })
    return rows


def degrade_image(source: Path, target: Path, tier: str, angle: float, seed: int) -> None:
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    target.parent.mkdir(parents=True, exist_ok=True)
    if tier == "clean":
        image.save(target, "PDF", resolution=150)
        return
    image = ImageOps.grayscale(image).convert("RGB") if seed % 2 == 0 else image
    image = ImageEnhance.Contrast(image).enhance(0.88 if tier == "moderate" else 0.62)
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(248, 247, 243))
    if tier == "moderate":
        image = image.filter(ImageFilter.GaussianBlur(radius=0.35))
        new_size = (int(image.width * 0.85), int(image.height * 0.85))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    else:
        image = image.filter(ImageFilter.GaussianBlur(radius=0.85))
        new_size = (int(image.width * 0.64), int(image.height * 0.64))
        image = image.resize(new_size, Image.Resampling.BILINEAR)
    jpg_path = target.with_suffix(".jpg")
    quality = 68 if tier == "moderate" else 38
    image.save(jpg_path, "JPEG", quality=quality, optimize=True)
    with Image.open(jpg_path) as compressed:
        compressed.convert("RGB").save(target, "PDF", resolution=150)
    jpg_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, choices=(1, 2, 3), default=1, help="1 or 2 creates a varied OCR set; 3 creates the clear, multi-item set")
    args = parser.parse_args()
    powershell = shutil.which("powershell")
    if not powershell:
        raise SystemExit("This generator currently requires Windows PowerShell 5.1.")
    records = build_records(args.batch)
    out_name = {1: "varied_invoices", 2: "varied_invoices_2", 3: "clear_invoices_20"}[args.batch]
    out = ROOT / "tests" / "fixtures" / "synthetic" / out_name
    manifest = out / "manifest.json"
    out.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
        "dataset": f"SecureFin Varied Synthetic Invoice OCR Set - Batch {args.batch}",
        "version": "1.0",
        "count": len(records),
        "synthetic_only": True,
        "license": "CC0-1.0",
        "languages": {language: sum(row["language"] == language for row in records) for language in ("ar", "en", "mixed")},
        "quality_tiers": {tier: sum(row["quality_tier"] == tier for row in records) for tier in QUALITY},
        "layout_count": 10,
        "notes": "All pages are clean, full-resolution renders with no blur, skew, contrast reduction, downsampling, or JPEG compression." if args.batch == 3 else "Some pages are intentionally low contrast, skewed, blurred, downsampled, and JPEG-compressed. The quality_tier field indicates the intended difficulty.",
        "records": records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    work_dir = ROOT / ".tmp-varied-invoices"
    work_dir.mkdir(exist_ok=True)
    renderer = ROOT / "data" / "scripts" / "render_varied_synthetic_invoices.ps1"
    with tempfile.TemporaryDirectory(prefix="securefin-varied-", dir=work_dir) as temp_name:
        temp = Path(temp_name)
        subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(renderer), "-Manifest", str(manifest), "-OutputDirectory", str(temp)], check=True)
        for row in records:
            degrade_image(
                temp / f"{Path(str(row['file'])).stem}.png",
                out / str(row["file"]),
                str(row["quality_tier"]),
                float(row["simulated_rotation_degrees"]),
                int(str(row["id"]).split("-")[-1]),
            )
    print(f"Created {len(records)} varied synthetic invoice PDFs in {out}")
    print(f"Ground truth: {manifest}")


if __name__ == "__main__":
    main()
