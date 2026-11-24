# eval/ — Evaluation harness (owner: M4 Ziad)

- `attack_suite/` — 100 labelled attacks, one JSON per case: 35 prompt injection (A), 25 self-approval /
  approval abuse (B), 20 bank-detail swap (C), 20 audit / approval tampering (D).
  `{"id", "scenario", "category", "description", "input", "expected", "unsafe_if", "attack"}`.
  `input` describes the attack for people; `attack` makes it executable:
  - `kind`: `invoice` (text through the real extractor, risk features, risk score, gateway), `agent_action`
    (proposals straight to the gateway), `approval_flow` (api + gateway approval and execute endpoints),
    `sql` (statements under the database roles, or the hash-chain check), `not_executable` (with `reason`).
  - `success_if`: which outcomes mean the attack worked (`executed`, `executed_twice`, `paid_to_attacker_iban`,
    `not_flagged`, `approved`, `stored`, `undetected`).
  - `llm_fields` / `proposes`: what a fully hijacked model emits. The run assumes the worst model, so it measures
    the controls, not the model.
  - `known_gap`: set only on a case that still gets through, with the reason (see the report).
  `expected` is the outcome with the controls on (`BLOCK`, `PENDING_APPROVAL`, `FLAGGED`, `NEEDS-REVIEW`, `DENIED`,
  `NO_ROWS` for a read or write that touches nothing, `CHAIN_BROKEN`).
- `asr_harness.py` + `run_asr.py` — run every case with the controls **on** and **off** and report the attack
  success rate (ASR). Controls off = no gateway, no database roles / row-level security / append-only trigger,
  no hash-chain check; extractor checks and risk features still run.
  `ASR_REPORT.md` is the latest run (regenerate it, do not edit it). CI job `eval` runs the suite on every PR and
  fails if an attack gets through that is not a documented gap. `tests/test_attack_suite.py` checks every file.

  ```powershell
  python eval/run_asr.py                                   # in-memory cases (SQL cases are skipped)
  $env:ASR_DATABASE_URL = "postgresql+psycopg://postgres:pw@localhost:5432/postgres"
  python eval/run_asr.py --report eval/ASR_REPORT.md       # all 100; creates a database called securefin_asr
  ```
- `legit_set/` — normal requests & invoices (measures false-block rate).
- `ocr_benchmark.py` — runs either Tesseract (`ara+eng`) or PaddleOCR on the 130 image-only invoice PDFs and writes per-invoice field-hit and latency results under ignored `eval/results/`. PaddleOCR sorts Arabic word boxes right-to-left, runs Arabic and English recognition on Arabic/mixed pages, and defaults to a sharpened 2x grayscale OCR pass on the supplier header. The full-page grayscale/autocontrast/upscale/sharpen experiment (`--preprocess enhance`) reduced PaddleOCR accuracy, so original images remain the default outside the targeted header crop.
- `--paddle-item-crop-pass` — optional experimental 2x OCR pass on the middle/lower invoice region. On the current synthetic set it improved normalized field recall from 96.5% to 96.7%, while increasing mean CPU time from 4.68 to 9.60 seconds per invoice. It is off by default until downstream extraction precision is checked; see `OCR_BENCHMARK.md`.
- `--paddle-focused-fields-pass` — adds 3x crops for the Arabic header, RTL description column, and lower-right amount area. On the 33-invoice failed subset, it raised normalized recall from 89.0% to 90.5% with no field regressions, while increasing mean latency from 8.34 to 14.75 seconds/page. It remains opt-in; see `OCR_BENCHMARK.md`.
- `--invoice-id ID...` — run a selected manifest invoice subset for targeted OCR comparisons.
- `rescore_ocr_results.py` — recalculates field-hit metrics from existing raw CSVs without rerunning OCR; writes separate `*_rescored.csv` files and preserves raw OCR output.
- `review_ocr_failures.py` — generates a per-invoice report of missed fields, expected values, and the closest OCR text snippet for manual review; it does not edit OCR output or invoice PDFs.
- `OCR_FAILURE_REVIEW.md` — current 130-invoice error register with 33 remaining invoices and 67 missed fields after the experimental crop pass.
- `OCR_MANUAL_CORRECTIONS.csv` — source-page audit of those 67 misses; separates 60 visually confirmed values, six uncertain low-resolution descriptions, and one PDF/manifest label mismatch. It does not replace raw OCR.
- `OCR_VERIFIED_CORRECTIONS.md` — visual review notes and the STRESS-004 fixture discrepancy.
- `export_manual_ocr_corrections.py` — regenerates the manual correction ledger from benchmark output and review status annotations.
- `OCR_BENCHMARK.md` — dataset inventory, normalization rules, and metric limits.

## Run the OCR comparison

Install the Python reader dependencies and install one candidate engine:

```powershell
python -m pip install -r eval/requirements-ocr.txt
python eval/ocr_benchmark.py --engine tesseract --set all
python eval/ocr_benchmark.py --engine paddleocr --set all
```

Tesseract must include both `ara` and `eng` language data and be on `PATH`. PaddleOCR uses PP-OCRv5 Arabic and English models (both on mixed pages); its first run may download models. Follow [the official PaddleOCR installation and OCR API guide](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html) to install a CPU-compatible PaddlePaddle/PaddleOCR build.

Choose `--set original`, `--set varied-1`, `--set varied-2`, or `--set clear-20` to score a subset. `--set all` runs all 130 invoices. The output CSV contains raw recognized text and per-field hit details; keep it local because OCR output can contain sensitive document text when the source set is later replaced with real invoices.

For Tesseract layout experiments, `--tesseract-psm 11` selects sparse-text segmentation. It performed worse than the default PSM 6 on this invoice set. To skip PaddleOCR's extra header pass for faster runs, use `--no-paddle-vendor-header-pass`. See `OCR_BENCHMARK.md` for the measured comparison.

The benchmark reports structured field-hit rate, not full-page CER/WER: the manifests do not contain a complete transcription of every printed line. See `OCR_BENCHMARK.md` for the limits and grouping fields.

After updating the scoring logic, rescore existing engine output with:

```powershell
python eval/rescore_ocr_results.py
```

Numeric matches are compared as complete number tokens so adjacent values cannot join into one. Decimal currency tokens can still match when the OCR attached a stray letter immediately before the amount; integer fields keep strict boundaries. See `OCR_BENCHMARK.md` for the detailed scoring notes.
