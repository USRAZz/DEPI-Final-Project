# Varied synthetic invoice OCR set - batch 2

This is an additional 30-invoice set, separate from both the original 50 and the first varied set. It contains 10 Arabic, 10 English, and 10 mixed-language invoices across 10 layouts. Invoices have one to five line items, with quantities, unit prices, calculated subtotals, and 14% VAT.

The set has 10 each of `clean`, `moderate`, and `hard` image quality. The harder samples use lower contrast, grayscale, skew, blur, downsampling, and JPEG compression. Use `manifest.json` to see each invoice's language, layout, quality tier, and ground-truth fields.

All business names and invoice data are invented. Account strings are invalid placeholders. Do not use these documents for payment or tax filing. The files are safe for the course team's repository and released under CC0-1.0.

Regenerate this batch on Windows with Python, Pillow, and Windows PowerShell 5.1 installed:

```powershell
python data/scripts/generate_varied_synthetic_invoices.py --batch 2
```

The PDFs contain raster page images without a selectable text layer.
