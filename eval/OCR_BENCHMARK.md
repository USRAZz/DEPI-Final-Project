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

### Service OCR check (2026-11-10)

`eval/service_ocr_check.py` scores what `services/extractor/app/ocr.py` actually runs, with the same normalized scoring, on all 130 invoices.

| Service configuration | Field hits | Vendor | Descriptions | Quantity | Mean time/page |
|---|---:|---:|---:|---:|---:|
| Before: 200 dpi render, full-page ar + en | 1,962/2,032 (96.6%) | 124/130 | 171/228 | 225/228 | 11.24 s |
| After: embedded scan at native size + Arabic header pass | **1,964/2,032 (96.7%)** | **126/130** | 168/228 | **228/228** | **8.79 s** |

Per invoice: vendor fixed on INV-003/013/042, STRESS-016/025, STRESS3-012; vendor lost on INV-008, STRESS-022, STRESS3-007, STRESS3-013; three descriptions and one tax value lost. Net +2 fields and 22% faster.

**Review of every remaining miss (2026-11-10).** The raw OCR text of the 29 invoices with misses was compared with the expected values (`--invoice-id ... --save-text DIR`). Causes:

1. *Header merge, 4 vendors.* The full page and the 2x header crop split text differently: one box `شركة المرسى للخدمات` against three word boxes. The old merge compared single words, so one surer word replaced the whole phrase (word order broke on STRESS3-007/013) or crop words were added twice (`مكتبة مكتبة ال الصفوة` on INV-008). On STRESS-022 the crop dropped a letter (`السنبة`) but scored 0.03 higher and won.
2. *Letters inside amounts, 1 tax.* `1,521.B0` on STRESS-003.
3. *Arabic item descriptions in degraded table cells, 60 fields.* The recognizer drops dots and thin strokes (`خمة` for `خدمة`, `اسشاربة` for `استشارية`); on the two bilingual STRESS-030 / STRESS2-030 pages whole cells are lost. Re-reading the whole page enhanced and enlarged 2x did not help (3/19 descriptions before and after on six such invoices) and took 3x longer, so this is a recognition limit on these images, not a merge problem. The downstream LLM extraction sees the misspelled text; it is not fixed in OCR.

Fixes in `ocr.py`: overlapping boxes from the two passes are compared as one group, read right to left. The crop group replaces the full-page group only when the full page mixed a Latin letter into Arabic or the crop's mean score is higher by `HEADER_MARGIN` = 0.05. Differing Latin readings (ids, IBANs) are both kept. Amount-shaped tokens with at least three digits get `B O o S l I` read as digits. The margin was tuned on cached raw output of all 130 invoices (0.03 and 0.05 tie; 0.0, 0.02 and 0.1 lose one vendor each).

| Service configuration (fresh run on all 130) | Field hits | Vendor | Account | Tax | Descriptions | Mean time/page |
|---|---:|---:|---:|---:|---:|---:|
| Before (200 dpi, full page ar + en) | 1,962/2,032 (96.6%) | 124/130 | 130/130 | 129/130 | 171/228 | 11.24 s |
| Header pass, word-level merge | 1,964/2,032 (96.7%) | 126/130 | 130/130 | 129/130 | 168/228 | 8.79 s |
| Header pass, group merge + amount fix | **1,969/2,032 (96.9%)** | **130/130** | **130/130** | **130/130** | 168/228 | 9.24 s |

Every field outside the item table now matches on all 130 invoices. The 63 remaining misses are 60 Arabic descriptions and 3 line totals, all in the item table of STRESS-tier pages (STRESS-004 line 2 is a label mismatch, see above).

**Experiments on the 60 remaining Arabic descriptions (2026-11-10), none adopted.** The pages that miss are small scans (median 793x1122 px, about 96 dpi; Arabic table lines 10-23 px tall vs 35 px on the clean INV pages), so the strokes are not in the image.

| Experiment (26 invoices with description misses) | Arabic descriptions / other effect | Time |
|---|---|---|
| Recognizer-only re-read of each table line crop: plain, 2x, 2x/3x stroke thickening, Otsu, median+sharpen, gamma darken | best 7/68 vs 8/68 baseline | ~3 s/26 pages |
| Embedded scan (current) vs PDF render at 200 / 300 dpi | descriptions 11 / 14 / 20 of 71, but total 455 / 453 / 453 of 518 (vendors and amounts lost) | 7.1 / 9.9 / 17.7 s/page |
| Local vision LLM via Ollama: gemma4:e4b, qwen3.8 | gemma: "no Arabic text"; qwen3.8 read `خدمة صيانة` as `خدمة عمولة` (invented a plausible word) | 52 s/line |

Only `arabic_PP-OCRv5_mobile_rec` exists for Arabic in PaddleOCR (no server model). Candidates not tried (need multi-GB downloads): QARI-OCR (Qwen2-VL-2B fine-tuned on degraded Arabic) and PaddleOCR-VL. A VLM that guesses words is risky for amounts and names; if tried, use it only for descriptions and keep the PaddleOCR reading next to it.

**QARI-OCR second reading (2026-11-12, opt-in `OCR_ARABIC_REREAD=qari`).** [QARI-OCR v0.3](https://huggingface.co/NAMAA-Space/Qari-OCR-v0.3-VL-2B-Instruct) is Qwen2-VL-2B fine-tuned on degraded Arabic print. Run on an RTX 5070 Ti (fp16).

| QARI setup (26 pages with description misses) | All fields | Arabic descriptions | Notes |
|---|---:|---:|---|
| PaddleOCR only | 455/518 | 11/71 | |
| QARI per table line, replacing Paddle | 39/46 on 2 pages, no gain | 0/7 | single lines are out of its training: HTML tags, Chinese, prompt echoed |
| QARI on the whole table region, 300 dpi render | 54/63 on 3 pages, no gain | 0/9 | skipped the description column |
| QARI on the whole table region, embedded scan, text **added** after Paddle's | 475/518 | 30/71 | +1 amount came from QARI |
| Same, QARI amount tokens dropped (adopted) | 474/518 | 30/71 | all gains are descriptions |

QARI alone is worse than PaddleOCR (254/518) and invents plausible words (`خدمة مالية` for `خدمة معايرة`, `اللبنان` for `البيان`), so it never replaces PaddleOCR. The service adds its reading after a marker line (`REREAD_MARKER`), with amounts removed, so every number still comes from PaddleOCR. It runs only when the weakest Arabic line below the header scored under `REREAD_SCORE` = 0.8 (catches 21 of the 26 bad pages; mean score would catch 11).

| All 130 invoices (cached PaddleOCR output, identical to the fresh service run, + the real `needs_reread` / `qari_table_lines`) | Field hits | Descriptions | QARI pages | Extra time |
|---|---:|---:|---:|---:|
| PaddleOCR (default) | 1,969/2,032 (96.9%) | 168/228 | 0 | 0 |
| + QARI second reading | **1,985/2,032 (97.7%)** | **184/228** | 41/130 | 10.9 s per re-read page (~3.4 s/page on average) |

No non-description field changed. Off by default because it adds torch + transformers and a 4.5 GB model to the extractor, needs a GPU to be practical, and the downstream LLM extraction has not yet been measured on text that contains a second, possibly wrong, reading. Precision of the extracted fields must be checked before turning it on.

**Does the QARI reading help the LLM extraction? (2026-11-13).** The real `pipeline.process_invoice` (masking, extractor prompt, checks) was run on the 41 pages where QARI runs, once with the PaddleOCR text and once with the QARI block added. The extractor LLM was a local `qwen3:8b` through Ollama's OpenAI-compatible endpoint (the project `.env` has no OpenAI key or model yet), so absolute numbers are not the production model's. Gate threshold 0.85 was also tried: 1,986 vs 1,985 field hits but QARI on 54 pages instead of 41, so `REREAD_SCORE` stays 0.8.

| Extracted field (41 pages) | PaddleOCR text | + QARI block |
|---|---:|---:|
| Line descriptions | 59/106 | **71/106** |
| Date / invoice number | 40/41, 40/41 | 41/41, 41/41 |
| Line totals / total / tax | 104/106, 41/41, 37/41 | 104/106, 41/41, 37/41 |
| Subtotal | 41/41 | 40/41 |
| Vendor | 28/41 | 25/41 |
| All | 390/458 | **400/458** |

Descriptions gain clearly. The vendor changes go both ways (4 won, 7 lost) although the QARI block covers only the table and holds no vendor text, and the same invoice gave different losses on two runs (STRESS-004: tax in one, vendor and subtotal in the other), so these look like run-to-run variation of the local model, not QARI misleading it. Before turning `OCR_ARABIC_REREAD=qari` on, repeat this with the production extractor model and run each variant at least twice to measure that variation. Scripts: `extract_eval.py`, `cache_qari.py`, `full_check.py` (kept outside the repo).
