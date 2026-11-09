# Clear synthetic invoice set - 20 multi-item invoices

This collection contains 20 fully synthetic, high-resolution invoices. Every invoice has 2 to 5 line items with quantities and unit prices, a calculated subtotal, and 14% VAT. The set covers Arabic, English, and mixed Arabic-English invoices across ten visual layouts. The language split is recorded in `manifest.json`.

All images are rendered cleanly at full resolution. There is no intentional skew, blur, grayscale conversion, contrast reduction, downsampling, or JPEG compression. Use this set as a clear-image comparison set beside the two varied OCR sets.

All supplier names, invoice data, account strings, and registration numbers are invented. The account strings are invalid placeholders. These fixtures are not for payment or tax filing and are safe to share with the course team under CC0-1.0.

Regenerate on Windows with Python, Pillow, and Windows PowerShell 5.1 installed:

```powershell
python data/scripts/generate_varied_synthetic_invoices.py --batch 3
```

The PDFs contain image-only pages, with no selectable text layer.
