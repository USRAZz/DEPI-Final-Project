"""Score the extractor SERVICE's OCR (services/extractor/app/ocr.py) on the synthetic manifests.

ocr_benchmark.py measures OCR configurations; this measures what production actually runs, with the
same scoring (normalized field hits). Run it in the PaddleOCR environment:

    python eval/service_ocr_check.py --set all --out eval/results/service_ocr.csv
"""
import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.ocr_benchmark import DATASETS, expected_fields, has_value, load_records  # noqa: E402
from services.extractor.app.ocr import extract_text_and_confidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="dataset", choices=("all", *DATASETS), default="all")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results" / "service_ocr.csv")
    args = parser.parse_args()

    records = load_records(args.dataset)[: args.limit or None]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    hits = total = 0
    seconds = []
    groups: dict[str, list[int]] = {}
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["set", "invoice", "hits", "fields", "seconds", "missed"])
        for name, pdf, row in records:
            start = time.perf_counter()
            text, _ = extract_text_and_confidence(pdf)
            seconds.append(time.perf_counter() - start)
            expected = expected_fields(row)
            ok = {k: any(has_value(text, v, fold_arabic=True) for v in vals) for k, vals in expected.items()}
            for k, good in ok.items():
                g = groups.setdefault(k.split("_")[-1] if k.startswith("line_") else k, [0, 0])
                g[0] += good
                g[1] += 1
            hits += sum(ok.values())
            total += len(ok)
            w.writerow([name, pdf.stem, sum(ok.values()), len(ok), round(seconds[-1], 2),
                        " ".join(k for k, good in ok.items() if not good)])
            print(f"{pdf.stem}: {sum(ok.values())}/{len(ok)} in {seconds[-1]:.1f}s", flush=True)
    print(f"\nTOTAL {hits}/{total} = {100 * hits / total:.1f}%  mean {sum(seconds) / len(seconds):.2f}s/page")
    for k, (g, n) in sorted(groups.items()):
        print(f"  {k:<16} {g}/{n} = {100 * g / n:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
