"""Recalculate OCR field metrics from existing raw benchmark CSVs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ocr_benchmark import has_value

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "eval" / "results"


def rescore(source: Path) -> tuple[Path, int, int, int]:
    destination = source.with_name(f"{source.stem}_rescored{source.suffix}")
    with source.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError(f"Missing CSV header: {source}")
        rows = list(reader)

    total_fields = strict_hits = normalized_hits = 0
    for row in rows:
        details = json.loads(row["field_details_json"])
        text = row["recognized_text"]
        for values in details.values():
            expected = values["expected"]
            values["strict_hit"] = any(
                has_value(text, value, fold_arabic=False) for value in expected
            )
            values["normalized_hit"] = any(
                has_value(text, value, fold_arabic=True) for value in expected
            )

        count = len(details)
        strict_count = sum(item["strict_hit"] for item in details.values())
        normalized_count = sum(item["normalized_hit"] for item in details.values())
        total_fields += count
        strict_hits += strict_count
        normalized_hits += normalized_count
        row["strict_hits"] = str(strict_count)
        row["strict_field_hit_rate"] = f"{strict_count / max(count, 1):.4f}"
        row["normalized_hits"] = str(normalized_count)
        row["normalized_field_hit_rate"] = f"{normalized_count / max(count, 1):.4f}"
        row["field_details_json"] = json.dumps(details, ensure_ascii=False)

    with destination.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return destination, len(rows), strict_hits, normalized_hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        default=[
            DEFAULT_RESULTS / "ocr_paddleocr_all.csv",
            DEFAULT_RESULTS / "ocr_tesseract_all.csv",
        ],
        help="Raw benchmark CSVs; defaults to both full dataset results.",
    )
    args = parser.parse_args()

    for source in args.files:
        destination, invoices, strict_hits, normalized_hits = rescore(source)
        with destination.open("r", encoding="utf-8-sig", newline="") as stream:
            total_fields = sum(
                len(json.loads(row["field_details_json"]))
                for row in csv.DictReader(stream)
            )
        print(
            f"{destination}: {invoices} invoices; "
            f"strict {strict_hits}/{total_fields} ({strict_hits / total_fields:.1%}); "
            f"normalized {normalized_hits}/{total_fields} ({normalized_hits / total_fields:.1%})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
