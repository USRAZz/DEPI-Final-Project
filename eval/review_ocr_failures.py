"""Create a per-invoice OCR failure review from a rescored benchmark CSV."""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "eval/results/ocr_paddleocr_all_header_items_experimental_rescored.csv"
DEFAULT_OUTPUT = ROOT / "eval/OCR_FAILURE_REVIEW.md"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(
        str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    )
    value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))
    return "".join(
        char.casefold()
        for char in value
        if char != "ـ" and unicodedata.category(char) not in {"Mn", "Cf"} and char.isalnum()
    )


def candidates(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = list(lines)
    for width in (2, 3, 4):
        result.extend(" ".join(lines[index : index + width]) for index in range(len(lines) - width + 1))
    return list(dict.fromkeys(result))


def best_candidate(expected: str, options: list[str]) -> tuple[float, str]:
    needle = normalize(expected)
    if not needle:
        return 0.0, ""
    ranked = [
        (difflib.SequenceMatcher(None, needle, normalize(option), autojunk=False).ratio(), option)
        for option in options
        if normalize(option)
    ]
    return max(ranked, default=(0.0, ""), key=lambda item: item[0])


def classification(field: str, score: float) -> str:
    if field.endswith("_description") or field == "vendor":
        if score >= 0.78:
            return "near-read: likely character confusion or a split word"
        return "weak read: needs image/layout-specific review"
    if score >= 0.9:
        return "near-read: likely digit or separator confusion"
    return "weak read: needs image/layout-specific review"


def create_report(source: Path, destination: Path) -> tuple[int, int]:
    by_invoice: dict[str, dict[str, object]] = {}
    with source.open("r", newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    catalogs: dict[str, set[str]] = {"vendor": set(), "description": set()}
    for row in rows:
        details = json.loads(row["field_details_json"])
        for field, detail in details.items():
            catalog = "vendor" if field == "vendor" else "description" if field.endswith("_description") else ""
            if catalog:
                catalogs[catalog].update(str(value) for value in detail["expected"])

    for row in rows:
        details = json.loads(row["field_details_json"])
        missed = [(name, detail) for name, detail in details.items() if not detail["normalized_hit"]]
        if missed:
            by_invoice[row["invoice_id"]] = {"row": row, "missed": missed}

    lines = [
        "# PaddleOCR failure review",
        "",
        f"Source: `{source.relative_to(ROOT).as_posix()}`. This report is generated from OCR output and manifest labels; it does not change invoice PDFs or OCR text.",
        "",
        "Similarity is a review hint, not proof of a correction. High scores usually mean the recognizer produced a close typo or split text; low scores need a visual review. Keep the original OCR text alongside any later suggested field value.",
        "",
        "Lexicon suggestions use the synthetic fixture vocabulary as a catalog and are printed only when the expected term ranks first with a score of at least 0.78 and an 0.08 margin. This is an assistive synthetic-data review, not a raw-OCR score or a general vendor/product catalog.",
        "",
        f"Invoices with at least one missed field: {len(by_invoice)}.",
        "",
    ]
    total_misses = 0
    for invoice_id, group in by_invoice.items():
        row = group["row"]
        missed = group["missed"]
        total_misses += len(missed)
        lines.extend(
            [
                f"## {invoice_id}",
                "",
                f"Language: `{row['language']}`; quality: `{row['quality_tier']}`; layout: `{row['layout_variant']}`; dataset: `{row['dataset']}`.",
                "",
            ]
        )
        options = candidates(row["recognized_text"])
        for field, detail in missed:
            expected_values = detail["expected"]
            ranked = sorted(
                [
                    (score, expected, observed)
                    for expected in expected_values
                    for score, observed in [best_candidate(expected, options)]
                ],
                reverse=True,
            )
            score, expected, observed = ranked[0] if ranked else (0.0, "", "")
            lines.append(
                f"- **{field}** — expected `{expected}`; closest OCR: `{observed}` ({score:.2f}). {classification(field, score)}."
            )
            catalog_name = "vendor" if field == "vendor" else "description" if field.endswith("_description") else ""
            if catalog_name:
                suggestions = sorted(
                    [
                        (candidate_score, value, candidate_text)
                        for value in catalogs[catalog_name]
                        for candidate_score, candidate_text in [best_candidate(value, options)]
                    ],
                    reverse=True,
                )
                top = suggestions[0] if suggestions else (0.0, "", "")
                second_score = suggestions[1][0] if len(suggestions) > 1 else 0.0
                margin = top[0] - second_score
                expected_keys = {normalize(value) for value in expected_values}
                if normalize(top[1]) in expected_keys and top[0] >= 0.78 and margin >= 0.08:
                    lines.append(
                        f"  - Synthetic-catalog suggestion: `{top[1]}` ({top[0]:.2f}, margin {margin:.2f}); verify against the PDF before applying."
                    )
                else:
                    lines.append("  - Synthetic-catalog suggestion: no safe match; review the source image.")
        lines.append("")

    lines.extend([f"Total missed fields: {total_misses}.", ""])
    destination.write_text("\n".join(lines), encoding="utf-8")
    return len(by_invoice), total_misses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    invoice_count, missed_count = create_report(args.input, args.output)
    print(f"Wrote {args.output}: {invoice_count} invoices, {missed_count} missed fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
