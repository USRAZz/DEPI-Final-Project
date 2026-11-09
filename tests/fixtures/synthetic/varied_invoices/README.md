# Varied synthetic invoice OCR set

This is a second fixture set, separate from the original 50. It contains 30 fully synthetic one-page invoice scans: 10 Arabic, 10 English, and 10 mixed-language. The set spans 10 layouts and mixes single-item invoices with invoices containing 2 to 5 line items.

Image quality is intentionally varied. `clean`, `moderate`, and `hard` samples include different combinations of reduced contrast, grayscale, skew, blur, downsampling, and JPEG compression. Use the `quality_tier`, `layout_variant`, and `line_items` fields in `manifest.json` when grouping OCR results. The manifest is the ground truth; totals are calculated from the item quantities, unit prices, and 14% VAT.

Names and every identifier, account string, order number, date, and amount are invented. Account strings are invalid placeholders. These documents must not be used for payment or tax filing. They are safe for the course team's GitHub repository and released under CC0-1.0.

Regenerate on Windows with Python and Pillow installed:

```powershell
python data/scripts/generate_varied_synthetic_invoices.py
```

The PDFs contain raster page images without a selectable text layer. The script uses Windows PowerShell 5.1 for Arabic text rendering.
