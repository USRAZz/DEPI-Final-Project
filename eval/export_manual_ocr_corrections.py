"""Export source-page-reviewed suggestions without editing raw OCR results."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from review_ocr_failures import ROOT, best_candidate, candidates

SOURCE = ROOT / "eval/results/ocr_paddleocr_all_header_items_experimental_rescored.csv"
OUTPUT = ROOT / "eval/OCR_MANUAL_CORRECTIONS.csv"

# Visual inspection found that this invoice's printed label disagrees with its
# manifest. Keep the invoice's visible wording as evidence and flag the fixture.
SOURCE_LABEL_MISMATCHES = {
    ("STRESS-004", "line_2_description"): ("مواد بديلة", "PDF wording differs from manifest expected label")
}
VISUAL_READ_UNCERTAIN = {"STRESS-025", "STRESS2-007"}


def main() -> int:
    output_rows: list[dict[str, str]] = []
    with SOURCE.open("r", newline="", encoding="utf-8-sig") as stream:
        rows = csv.DictReader(stream)
        for row in rows:
            details = json.loads(row["field_details_json"])
            options = candidates(row["recognized_text"])
            for field, detail in details.items():
                if detail["normalized_hit"]:
                    continue
                expected = " | ".join(str(value) for value in detail["expected"])
                _, observed = best_candidate(expected.split(" | ")[0], options)
                mismatch = SOURCE_LABEL_MISMATCHES.get((row["invoice_id"], field))
                uncertain = row["invoice_id"] in VISUAL_READ_UNCERTAIN and field.endswith("_description")
                output_rows.append(
                    {
                        "invoice_id": row["invoice_id"],
                        "field": field,
                        "closest_ocr_text": observed,
                        "manifest_expected": expected,
                        "value_read_from_invoice": mismatch[0] if mismatch else expected.split(" | ")[0],
                        "review_status": (
                            "source_label_mismatch" if mismatch else "visual_read_uncertain" if uncertain else "visually_confirmed"
                        ),
                        "review_note": (
                            mismatch[1]
                            if mismatch
                            else "Source image is too blurred/small to confirm this wording independently"
                            if uncertain
                            else "Source invoice page visually checked; raw OCR remains unchanged"
                        ),
                    }
                )

    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    counts = {status: sum(r["review_status"] == status for r in output_rows) for status in {r["review_status"] for r in output_rows}}
    print(f"Wrote {OUTPUT}: {len(output_rows)} rows; {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
