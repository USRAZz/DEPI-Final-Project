# Visually verified OCR correction suggestions

These suggestions were checked against the rendered source invoice pages. They are a separate review artifact: they do not rewrite raw PaddleOCR output, benchmark labels, invoice PDFs, or accuracy scores. The source is synthetic test data, so catalog-assisted matches are only valid for these fixtures. The field-by-field ledger for all 67 misses is `OCR_MANUAL_CORRECTIONS.csv`.

| Invoice | Field | OCR issue | Value visible in source |
|---|---|---|---|
| INV-002 | vendor | Extra character/word split | مؤسسة الأفق المكتبي |
| INV-008 | vendor | Extra word split | مكتبة الصفوة |
| INV-012 | vendor | Extra character/word split | مؤسسة الأفق المكتبي |
| INV-018 | vendor | Extra word split | النور للصيانة |
| STRESS-007 | line 3 description | Missing characters | خدمة صيانة |
| STRESS-013 | line 1 description | Character confusion | معدات شبكات |
| STRESS-014 | line 1 description | Character confusion | Packaging materials |
| STRESS2-005 | line 1 description | Character confusion | Delivery service |
| STRESS2-013 | line 2 description | Character confusion | خدمة معايرة |
| STRESS2-014 | line 1 description | Character confusion | Wrapping supplies |
| STRESS2-028 | line 1 description | Character confusion | قطع كهربائية |
| STRESS3-007 | vendor | Arabic characters misrecognized/split | مركز الإتقان للصيانة |
| STRESS3-018 | vendor | Arabic half of bilingual name missed | شركة المرسى للخدمات / Al Marsa Services |

## How to use this review

Treat the visible value as a human-verified suggestion for the listed synthetic fixture. Keep the original OCR text for auditability. Do not use these values as general production defaults for unknown invoices; a real system should use field confidence, validation, and human review when OCR is uncertain.

## Still unresolved

The full 67-field visual audit is now in `OCR_MANUAL_CORRECTIONS.csv`, with the closest OCR text, manifest reference, value read from the invoice, and a review status for every missed field. Sixty values were visually confirmed; six descriptions in `STRESS-025` and `STRESS2-007` remain too blurred to independently verify; one field in `STRESS-004` is a source/manifest mismatch. See `OCR_FAILURE_REVIEW.md` for the complete per-invoice OCR evidence.

For `STRESS-004` line 2, the PDF visibly says `مواد بديلة`, while the manifest expects `مواد تعبئة` / `Packaging materials`. This is a fixture generation or labeling problem, not an OCR miss. The raw score should not be counted as an OCR failure for this field until the fixture or ground truth is corrected and the benchmark is rerun.

The CSV is a human review artifact and does not modify raw OCR output or the benchmark score. To improve general OCR rather than fit known synthetic labels, use it to target recognizer/preprocessing changes, then run a new comparable benchmark.
