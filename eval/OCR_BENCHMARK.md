# Week 2 OCR comparison plan

## Dataset

The current synthetic corpus has 130 one-page, image-only invoices:

| Set | Count | Main use |
|---|---:|---|
| `tests/fixtures/synthetic/invoices/` | 50 | Baseline fields and duplicate/account-risk cases; one line item each. |
| `tests/fixtures/synthetic/varied_invoices/` | 30 | Ten layouts, Arabic/English/mixed text, varied item counts, and clean/moderate/hard images. |
| `tests/fixtures/synthetic/varied_invoices_2/` | 30 | Independent second varied set with new supplier and invoice values. |
| `tests/fixtures/synthetic/clear_invoices_20/` | 20 | Clear full-resolution pages; every invoice has multiple line items. |

Each set has a `manifest.json` (the baseline 50-invoice set keeps it one directory above its PDFs). Use the manifest as the only ground truth; do not infer labels from filenames. Keep duplicate pairs together if a later train/evaluation split is created.

## Candidate engines

Compare Tesseract with Arabic and English language data against PaddleOCR configured for the same scripts. Run both on the exact same PDFs and machine. `services/extractor` still returns a stub, so OCR output comparison is separate from field extraction.

## Current synthetic runs

On 2026-11-04, both engines were rerun on all 130 PDFs after fixing numeric-token scoring. Neither engine had per-invoice failures. On the original images, PaddleOCR reached **93.7% (1,904/2,032 fields)** at 2.48 seconds/page; Tesseract with `ara+eng` and PSM 6 reached **79.1% (1,607/2,032)** at 0.39 seconds/page.

### Text preprocessing experiment

The optional `--preprocess enhance` mode converts the page to grayscale, applies autocontrast, enlarges pages whose longest edge is below 2,400 pixels, and sharpens the result. OCR was rerun over the same 130 PDFs:

| Engine/configuration | Field hits | Mean total time/page | Change from original |
|---|---:|---:|---:|
| PaddleOCR, original image | 1,904/2,032 (93.7%) | 2.48 s | baseline |
| PaddleOCR, enhanced image | 1,887/2,032 (92.9%) | 9.29 s | -0.8 pp |
| Tesseract PSM 6, original image | 1,607/2,032 (79.1%) | 0.39 s | baseline |
| Tesseract PSM 6, enhanced image | 1,635/2,032 (80.5%) | 0.77 s | +1.4 pp |
| Tesseract PSM 11, original image | 1,386/2,032 (68.2%) | 0.36 s | -10.9 pp |

The enhancement helps Tesseract slightly, but makes PaddleOCR slower and less accurate. The largest remaining PaddleOCR misses are line-item descriptions, especially on hard-quality pages. Keep PaddleOCR on original images as the current default; retain enhancement as an optional Tesseract experiment. PSM 6 is better than PSM 11 for these invoice layouts. Do not describe synthetic-fixture field hit rate as expected accuracy on real invoices.

### Arabic reading-order and second-pass experiment

PaddleOCR returns recognized text boxes in left-to-right x order, which reversed split Arabic company names. The benchmark now sorts Arabic boxes from right to left within each detected visual row. It also sends Arabic and mixed pages through both Arabic and English PP-OCRv5 recognition, because the English model can recover Latin digits and IDs on Arabic invoices. Finally, by default it runs a second 2x Arabic OCR pass on the top 42% of Arabic and mixed pages, using grayscale, autocontrast, and sharpening. This targeted treatment fixed two repeated errors where “مصنع” was read as “مصiع” on INV-036 and INV-046.

| PaddleOCR configuration | All fields | Arabic vendor strings | Numeric fields | Mean OCR time/page |
|---|---:|---:|---:|---:|
| Before reading-order fix, one model by language | 1,907/2,032 (93.8%) | 69/88 (78.4%) | 1,148/1,204 (95.3%) | 2.48 s |
| RTL ordering only | 1,912/2,032 (94.1%) | 79/88 (89.8%) | 1,148/1,204 (95.3%) | 2.55 s |
| RTL ordering + both models for Arabic/mixed | 1,955/2,032 (96.2%) | 79/88 (89.8%) | 1,191/1,204 (98.9%) | 3.20 s |
| Above + sharpened Arabic header crop (default) | **1,959/2,032 (96.4%)** | **86/88 (97.7%)** | **1,191/1,204 (98.9%)** | 4.61 s |

The final run had no failed invoices. Header crop pass adds text from the supplier area and can repeat text already seen on the full page. It matched 86 of 88 Arabic vendor strings; the remaining misses are STRESS3-007 and STRESS3-012. Overall fixture field matching is 96.4%. The expanded passes cost more CPU time, so use `--no-paddle-vendor-header-pass` when speed matters more than Arabic supplier recall. These numbers are fixture-specific, not real-world accuracy guarantees.

### Item-region crop experiment

On 2026-11-05, the current pipeline was run twice on the same 130 invoices: once with the usual full-page and supplier-header passes, and once with an additional sharpened 2x crop of the middle/lower page. The item crop is opt-in via `--paddle-item-crop-pass` and stays off by default because it nearly doubles CPU time and appends additional OCR text that has not been precision-scored by a downstream extractor.

| Same-code configuration | Normalized field hits | Strict field hits | Mean total time/page | Failed invoices |
|---|---:|---:|---:|---:|
| Full page + supplier-header crop | 1,961/2,032 (96.5%) | 1,960/2,032 (96.5%) | 4.68 s | 0 |
| Above + item-region crop | **1,965/2,032 (96.7%)** | **1,964/2,032 (96.7%)** | 9.60 s | 0 |

In the paired run, the additional pass recovered four fields with no field-level regressions: the account on STRESS-003; a line total on STRESS-030; quantity on STRESS3-014; and an Arabic item description on STRESS3-019. It did not resolve most Arabic item-description errors. After the pass, 67 fields still miss across 33 invoices: 57 item descriptions, six vendor fields, and four amounts. There are no invoice-processing failures. Keep this as an experimental benchmark option until a field-extraction/precision check shows that the extra, sometimes duplicated OCR text does not confuse downstream parsing.

The rescoring logic also accepts a complete decimal currency token when OCR noise is attached immediately before it (for example, `A7,432.80`). It still requires the full digits and two fractional digits, and integer fields keep strict token boundaries. Rescoring the same OCR outputs after this change corrected seven baseline field misses and three item-crop run misses that were scoring false negatives rather than OCR reading failures.

### Focused Arabic-description and amount crop experiment

On 2026-11-05, the 33 invoices with residual misses were rerun with the existing item crop plus an opt-in focused pass. It reads a 3x crop of the Arabic supplier header, the rightmost RTL item-description column, and the lower-right totals area. Against the same 609 expected fields from the previous item-crop output, it recovered nine fields and regressed none: four vendor fields (INV-002/008/012/018), the STRESS3-018 vendor, STRESS3-016 line 2 description, STRESS-022 line 5 description, and line totals in STRESS-030 and STRESS2-030.

| Failed-invoice subset, 33 invoices | Normalized field hits | Mean OCR time/page |
|---|---:|---:|
| Existing full-page + header + item crops | 542/609 (89.0%) | 8.34 s |
| Above + focused header, Arabic description, and amount crops | **551/609 (90.5%)** | 14.75 s |

The focused pass stays opt-in (`--paddle-focused-fields-pass`) because it increased time by 1.77x on this subset and appends new OCR readings without yet measuring downstream extraction precision. These subset figures are not whole-dataset scores. Detailed output is in the ignored file `eval/results/ocr_paddleocr_failed33_focused_rescored.csv`.

Visual review also found one ground-truth issue: STRESS-004 line 2 displays `مواد بديلة` in the PDF while its manifest expects `مواد تعبئة`. This is a fixture/label mismatch and should not be presented as an OCR miss. Six descriptions in STRESS-025 and STRESS2-007 remain too blurred for independent visual confirmation. The 67-field audit is in `OCR_MANUAL_CORRECTIONS.csv`.

The current merged PaddleOCR output was also checked directly for INV-036 and INV-046: both supplier fields match `مصنع اليسر للتعبئة`, the corrupted token `مصiع` is absent, and the Arabic supplier name is present once in the merged Arabic pass. The English supplier name also appears in the English pass as expected.

The remaining misses after the item-crop experiment are:

| Invoice | Missed fields |
|---|---|
| INV-002, INV-008, INV-012, INV-018 | vendor |
| STRESS-001 | line 1 description |
| STRESS-003 | tax, line 2–4 descriptions |
| STRESS-004 | line 2–3 descriptions |
| STRESS-005 | tax |
| STRESS-007 | line 1–4 descriptions |
| STRESS-013 | line 1–2 descriptions |
| STRESS-014 | line 1 description |
| STRESS-016 | line 1–3 descriptions |
| STRESS-021 | line 1 description |
| STRESS-022 | line 4–5 descriptions |
| STRESS-025 | line 1–2 descriptions |
| STRESS-028 | line 1 description |
| STRESS-030 | line 1–4 descriptions, line 4 total |
| STRESS2-003 | line 1–4 descriptions |
| STRESS2-004 | line 1–2 descriptions |
| STRESS2-005 | line 1 description |
| STRESS2-007 | line 1–4 descriptions |
| STRESS2-013 | line 1–2 descriptions |
| STRESS2-014 | line 1 description |
| STRESS2-016 | line 1–3 descriptions |
| STRESS2-025 | line 1–2 descriptions |
| STRESS2-028 | line 1 description |
| STRESS2-030 | line 1–5 descriptions, line 5 total |
| STRESS3-001 | line 2 description |
| STRESS3-007, STRESS3-018 | vendor |
| STRESS3-010 | line 1 description |
| STRESS3-016 | line 2–4 descriptions |
| STRESS3-019 | line 2 description |

For expected values and the closest OCR text snippet for each remaining field, see the generated [OCR_FAILURE_REVIEW.md](OCR_FAILURE_REVIEW.md). Candidate similarity is only a review hint and must not be treated as a correction without checking the source image.

## Report per engine

- Field hit rate for supplier, invoice number, date, tax id, purchase order, account string, subtotal, tax, and total.
- Line-item description-hit count as a proxy for detected line count, plus line-item field hit rate for description, quantity, unit price, and line total. The first 50 baseline manifest lacks full item-level labels, so line-item scoring is blank for that set.
- Results grouped by language, layout, quality tier, and number of items.
- Processing time per page and failure/empty-result rate.
- A review sheet with every wrong or missing field, not only an aggregate score.

The manifests contain structured field labels, not a full diplomatic transcription of every printed glyph. Therefore, a field hit rate is suitable for this comparison, but full-page CER/WER should not be reported as a true OCR error rate until line-by-line transcripts are added and human-checked. Image variation tests OCR robustness; it does not make the synthetic set representative of Egyptian business invoices.

## Fair run rules

1. Pin engine versions and language packs; record CPU/GPU and settings.
2. Run all 130 PDFs through each engine with the same image resolution. Do not change preprocessing between candidates.
3. Report clean and degraded subsets separately; do not hide hard-page failures in an overall average.
4. Normalize only for comparison: Unicode NFC, whitespace/punctuation, and Arabic digit forms. Keep a second strict score so Arabic spelling normalization does not hide OCR errors.
5. Select an OCR engine from measured results. Keep field extraction/KIE evaluation separate from text recognition: OCR output alone does not establish correct invoice fields.

## Reproducing preprocessing experiments

```bash
python eval/ocr_benchmark.py --engine paddleocr --set all --output eval/results/ocr_paddleocr_all_header_pass.csv
python eval/ocr_benchmark.py --engine paddleocr --set all --no-paddle-vendor-header-pass --output eval/results/ocr_paddleocr_all_no_header_pass.csv
python eval/ocr_benchmark.py --engine paddleocr --set all --paddle-item-crop-pass --output eval/results/ocr_paddleocr_all_item_crop_experiment.csv
python eval/ocr_benchmark.py --engine tesseract --set all --preprocess enhance --output eval/results/ocr_tesseract_all_enhanced.csv
python eval/ocr_benchmark.py --engine tesseract --set all --tesseract-psm 11 --output eval/results/ocr_tesseract_all_psm11.csv
```
