# Synthetic invoice OCR set

## Collections

- `invoices/` — the original 50 simple invoices, one line item per invoice.
- `varied_invoices/` — 30 invoices across ten layouts, mixed item counts, and varied image quality.
- `varied_invoices_2/` — another distinct 30-invoice set with the same language and quality balance, but different supplier and invoice data.
- `clear_invoices_20/` — 20 full-resolution, clean invoices, all with multiple line items.

The original 50 are fully synthetic, image-only invoice PDFs with `manifest.json` ground-truth fields. They have 20 Arabic, 15 English, and 15 bilingual invoices across five visual layouts. The manifest labels four actual duplicate pairs, six high-value review cases, and six invoice/vendor-account mismatch cases.

All names, tax identifiers, account strings, invoice numbers, and amounts are invented. The account strings are deliberately invalid test placeholders. Do not use these documents for payment, tax filing, or as evidence of performance on real invoices. These fixtures are safe to share with the course team and commit to GitHub.

Recreate the set on Windows with Python and Pillow installed:

```powershell
python data/scripts/generate_synthetic_invoices.py
```

The resulting PDFs are raster scans without an embedded text layer, so OCR engines must read the page image. `manifest.json` is the ground truth for field-level comparison. Generated fixtures are released under CC0-1.0.
