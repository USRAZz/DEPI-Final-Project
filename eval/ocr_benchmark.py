"""Compare OCR engines against the synthetic invoice manifests (no OCR model is bundled)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "original": ROOT / "tests/fixtures/synthetic/invoices",
    "varied-1": ROOT / "tests/fixtures/synthetic/varied_invoices",
    "varied-2": ROOT / "tests/fixtures/synthetic/varied_invoices_2",
    "clear-20": ROOT / "tests/fixtures/synthetic/clear_invoices_20",
}
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ARABIC_FOLDS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})
MONEY_KEYS = {"amount", "subtotal", "subtotal_egp", "tax", "tax_amount", "tax_egp", "total", "total_egp", "unit_price", "unit_price_egp", "line_total", "line_total_egp"}


def normalize(value: str, *, fold_arabic: bool) -> str:
    value = unicodedata.normalize("NFKC", value).translate(ARABIC_DIGITS)
    if fold_arabic:
        value = value.translate(ARABIC_FOLDS)
    chars = []
    for char in value:
        if char == "ـ" or unicodedata.category(char) in {"Mn", "Cf"}:
            continue
        if char.isalnum():
            chars.append(char.casefold())
    return "".join(chars)


def has_value(text: str, expected: str, *, fold_arabic: bool) -> bool:
    needle = normalize(expected, fold_arabic=fold_arabic)
    haystack = normalize(text, fold_arabic=fold_arabic)
    if not needle:
        return False
    if needle.isdigit():
        # Compare complete numeric tokens from the source text. Normalizing the
        # whole page first removes punctuation and joins neighboring values
        # (for example, "3\n920.00" becomes "392000"), causing false misses.
        digit_text = unicodedata.normalize("NFKC", text).translate(ARABIC_DIGITS)
        # Monetary OCR can attach stray letters to the amount (for example,
        # "A7,432.80" or "P.E16,950.00"). For decimal values, accept the
        # complete amount token after that noise while still requiring a
        # thousands/decimal separator and exactly two fractional digits.
        if re.search(r"[.,٫٬]\d{2}$", expected.strip()):
            tokens = re.findall(r"(?<!\d)\d[\d.,٫٬]*(?!\d)", digit_text)
            return any(
                re.sub(r"\D", "", token) == needle
                and bool(re.search(r"[.,٫٬]\d{2}$", token))
                for token in tokens
            )
        tokens = re.findall(r"(?<!\w)\d[\d.,،٫٬/\-]*(?!\w)", digit_text, flags=re.UNICODE)
        return any(re.sub(r"\D", "", token) == needle for token in tokens)
    return needle in haystack


def expected_fields(record: dict[str, Any]) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}

    def add(name: str, value: Any, *, key: str = "") -> None:
        if value is None or isinstance(value, bool):
            return
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None:
                continue
            if isinstance(item, dict):
                continue
            if key in MONEY_KEYS and isinstance(item, (int, float)):
                rendered = f"{item:,.2f}"
            else:
                rendered = str(item)
            fields.setdefault(name, []).append(rendered)

    language = record.get("language", "mixed")
    add("vendor", record.get("vendor_name_ar") if language == "ar" else record.get("vendor_name_en") if language == "en" else [record.get("vendor_name_ar"), record.get("vendor_name_en")])
    add("invoice_number", record.get("invoice_number") or record.get("invoice_no"))
    add("date", record.get("invoice_date") or record.get("date"))
    add("purchase_order", record.get("purchase_order"))
    add("tax_id", record.get("tax_id"))
    add("account", record.get("invoice_iban") or record.get("iban"))
    for source_key, output_key in (("subtotal_egp", "subtotal"), ("subtotal", "subtotal"), ("tax_egp", "tax"), ("tax_amount", "tax"), ("total_egp", "total"), ("total", "total"), ("amount", "total")):
        if source_key in record:
            add(output_key, record[source_key], key=source_key)
    for index, line in enumerate(record.get("line_items") or []):
        desc = line.get("description_ar") if language == "ar" else line.get("description_en") if language == "en" else [line.get("description_ar"), line.get("description_en")]
        add(f"line_{index + 1}_description", desc)
        for key in ("quantity", "unit_price_egp", "unit_price", "line_total_egp", "line_total"):
            if key in line:
                add(f"line_{index + 1}_{key}", line[key], key=key)
    return {name: list(dict.fromkeys(values)) for name, values in fields.items() if values}


def extract_image(pdf: Path, target: Path) -> Path:
    from pypdf import PdfReader

    page = PdfReader(str(pdf)).pages[0]
    images = list(page.images)
    if not images:
        raise RuntimeError(f"No embedded page image found in {pdf}")
    image = max(images, key=lambda item: len(item.data))
    suffix = Path(image.name).suffix or ".png"
    path = target / f"page{suffix}"
    path.write_bytes(image.data)
    return path


def preprocess_image(image: Path, mode: str) -> Path:
    """Apply conservative image cleanup before OCR; preserve the raw input."""
    if mode == "raw":
        return image

    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    with Image.open(image) as source:
        cleaned = ImageOps.grayscale(source)
        cleaned = ImageOps.autocontrast(cleaned, cutoff=1)
        # Small Arabic text benefits from enlargement; avoid shrinking already
        # large scans and use a high-quality resampler for the interpolation.
        scale = 2 if max(cleaned.size) < 2400 else 1
        if scale > 1:
            cleaned = cleaned.resize(
                (cleaned.width * scale, cleaned.height * scale),
                Image.Resampling.LANCZOS,
            )
        cleaned = ImageEnhance.Contrast(cleaned).enhance(1.15)
        cleaned = cleaned.filter(ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=3))
        output = image.with_name(f"{image.stem}_enhanced.png")
        cleaned.save(output, format="PNG", optimize=True)
    return output


class TesseractEngine:
    name = "tesseract-ara-eng"

    def __init__(self, page_segmentation_mode: int = 6) -> None:
        executable = shutil.which("tesseract")
        if not executable:
            raise RuntimeError("Tesseract is not installed or not on PATH. Install Tesseract with ara and eng language data.")
        self.executable = executable
        self.page_segmentation_mode = page_segmentation_mode
        languages = subprocess.run([executable, "--list-langs"], check=True, capture_output=True, text=True).stdout
        missing = {"ara", "eng"} - set(languages.split())
        if missing:
            raise RuntimeError(f"Tesseract language data missing: {', '.join(sorted(missing))}")

    def recognize(self, image: Path, language: str) -> tuple[str, float]:
        start = time.perf_counter()
        result = subprocess.run([self.executable, str(image), "stdout", "-l", "ara+eng", "--psm", str(self.page_segmentation_mode)], check=True, capture_output=True, text=True, encoding="utf-8")
        return result.stdout, time.perf_counter() - start


class PaddleEngine:
    name = "paddleocr-v5-ar-en"

    def __init__(
        self,
        *,
        vendor_header_pass: bool = True,
        item_crop_pass: bool = False,
        focused_fields_pass: bool = False,
    ) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError("PaddleOCR is not installed. Follow the official CPU install instructions, then install paddleocr.") from exc
        self.PaddleOCR = PaddleOCR
        self.engines: dict[str, Any] = {}
        self.vendor_header_pass = vendor_header_pass
        self.item_crop_pass = item_crop_pass
        self.focused_fields_pass = focused_fields_pass

    @staticmethod
    def ordered_texts(
        payload: dict[str, Any], *, right_to_left: bool
    ) -> list[str]:
        """Restore reading order for word boxes detected on the same visual line."""
        texts = [str(text) for text in payload.get("rec_texts", []) if text]
        boxes = payload.get("rec_boxes")
        if not isinstance(boxes, list) or len(boxes) != len(texts):
            return texts

        entries: list[tuple[float, float, float, float, str]] = []
        for text, box in zip(texts, boxes):
            if not isinstance(box, (list, tuple)) or len(box) < 4:
                return texts
            x1, y1, x2, y2 = (float(value) for value in box[:4])
            entries.append((x1, y1, x2, y2, text))

        rows: list[dict[str, Any]] = []
        for entry in sorted(entries, key=lambda item: ((item[1] + item[3]) / 2, item[0])):
            _, y1, _, y2, _ = entry
            height = max(y2 - y1, 1.0)
            best_row = None
            best_overlap = 0.0
            for row in rows:
                overlap = max(0.0, min(y2, row["bottom"]) - max(y1, row["top"]))
                ratio = overlap / min(height, max(row["bottom"] - row["top"], 1.0))
                if ratio > best_overlap:
                    best_overlap, best_row = ratio, row
            if best_row is not None and best_overlap >= 0.35:
                best_row["items"].append(entry)
                best_row["top"] = min(best_row["top"], y1)
                best_row["bottom"] = max(best_row["bottom"], y2)
            else:
                rows.append({"top": y1, "bottom": y2, "items": [entry]})

        ordered: list[str] = []
        for row in sorted(rows, key=lambda item: (item["top"] + item["bottom"]) / 2):
            row["items"].sort(
                key=lambda item: (item[0] + item[2]) / 2,
                reverse=right_to_left,
            )
            ordered.extend(item[4] for item in row["items"])
        return ordered

    @classmethod
    def merge_header_payloads(
        cls,
        full_payloads: list[dict[str, Any]],
        header_payloads: list[dict[str, Any]],
        *,
        page_height: float,
        scale: float = 2.0,
    ) -> list[str]:
        """Replace overlapping full-page Arabic detections with focused crop reads."""
        full_entries: list[tuple[str, list[float], float]] = []
        crop_entries: list[tuple[str, list[float], float]] = []

        def collect(
            payloads: list[dict[str, Any]],
            target: list[tuple[str, list[float], float]],
            divisor: float,
        ) -> bool:
            for payload in payloads:
                texts = payload.get("rec_texts", [])
                boxes = payload.get("rec_boxes", [])
                scores = payload.get("rec_scores", [])
                if not isinstance(boxes, list) or len(boxes) != len(texts):
                    return False
                for index, (text, box) in enumerate(zip(texts, boxes)):
                    if not text or not isinstance(box, (list, tuple)) or len(box) < 4:
                        continue
                    score = float(scores[index]) if index < len(scores) else 0.0
                    target.append((str(text), [float(value) / divisor for value in box[:4]], score))
            return True

        if not collect(full_payloads, full_entries, 1.0) or not collect(header_payloads, crop_entries, scale):
            combined = [*full_payloads, *header_payloads]
            return [
                text
                for payload in combined
                for text in cls.ordered_texts(payload, right_to_left=True)
            ]

        def overlap_fraction(box_a: list[float], box_b: list[float]) -> float:
            x1, y1, x2, y2 = box_a
            cx1, cy1, cx2, cy2 = box_b
            full_area = max(x2 - x1, 0) * max(y2 - y1, 0)
            crop_area = max(cx2 - cx1, 0) * max(cy2 - cy1, 0)
            if not full_area or not crop_area:
                return 0.0
            intersection = max(0.0, min(x2, cx2) - max(x1, cx1)) * max(
                0.0, min(y2, cy2) - max(y1, cy1)
            )
            return intersection / min(full_area, crop_area)

        merged_entries: list[tuple[str, list[float]]] = []
        used_crop: set[int] = set()
        for text, box, full_score in full_entries:
            x1, y1, x2, y2 = box
            matches = [
                (index, crop_entry)
                for index, crop_entry in enumerate(crop_entries)
                if (y1 + y2) / 2 < page_height * 0.42
                and overlap_fraction(box, crop_entry[1]) >= 0.45
            ]
            arabic_alternatives = [
                (index, crop_text, crop_box, crop_score)
                for index, (crop_text, crop_box, crop_score) in matches
                if any("\u0600" <= char <= "\u06ff" for char in crop_text)
                and not any(char.isascii() and char.isalpha() for char in crop_text)
            ]
            has_latin_letter_inside_arabic = bool(
                re.search(r"[\u0600-\u06ff][A-Za-z][\u0600-\u06ff]", text)
            )
            if has_latin_letter_inside_arabic and arabic_alternatives:
                replacement = " ".join(text for _, text, _, _ in arabic_alternatives)
                tokens = text.split()
                corrected_tokens = [
                    replacement
                    if any("\u0600" <= char <= "\u06ff" for char in token)
                    and any(char.isascii() and char.isalpha() for char in token)
                    else token
                    for token in tokens
                ]
                merged_entries.append((" ".join(corrected_tokens), box))
                used_crop.update(index for index, _ in matches)
            elif arabic_alternatives and any("\u0600" <= char <= "\u06ff" for char in text):
                best_crop = max(arabic_alternatives, key=lambda item: item[3])
                full_key = normalize(text, fold_arabic=True)
                crop_key = normalize(best_crop[1], fold_arabic=True)
                if crop_key == full_key:
                    merged_entries.append((text, box))
                    used_crop.add(best_crop[0])
                elif best_crop[3] > full_score + 0.01:
                    merged_entries.append((best_crop[1], box))
                    used_crop.add(best_crop[0])
                else:
                    merged_entries.append((text, box))
            else:
                merged_entries.append((text, box))
                full_key = normalize(text, fold_arabic=True)
                used_crop.update(
                    index
                    for index, (crop_text, _, _) in matches
                    if normalize(crop_text, fold_arabic=True) == full_key
                )
        merged_entries.extend(
            (text, box)
            for index, (text, box, _) in enumerate(crop_entries)
            if index not in used_crop
        )
        merged_payload = {
            "rec_texts": [text for text, _ in merged_entries],
            "rec_boxes": [box for _, box in merged_entries],
        }
        return cls.ordered_texts(merged_payload, right_to_left=True)

    def recognize(self, image: Path, language: str) -> tuple[str, float]:
        # The English recognizer is also useful on Arabic invoices: amounts,
        # invoice IDs, and Latin account strings are often clearer in that pass.
        model_languages = ["ar", "en"] if language in {"mixed", "ar"} else ["en"]
        for model_language in model_languages:
            if model_language not in self.engines:
                self.engines[model_language] = self.PaddleOCR(
                    lang=model_language,
                    ocr_version="PP-OCRv5",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    device="cpu",
                )
        start = time.perf_counter()
        arabic_payloads: list[dict[str, Any]] = []
        other_lines: list[str] = []
        for model_language in model_languages:
            results = self.engines[model_language].predict(str(image))
            for result in results:
                data = result.json
                if isinstance(data, str):
                    data = json.loads(data)
                payload = data.get("res", data) if isinstance(data, dict) else {}
                if self.vendor_header_pass and language in {"ar", "mixed"} and model_language == "ar":
                    arabic_payloads.append(payload)
                else:
                    other_lines.extend(self.ordered_texts(payload, right_to_left=model_language == "ar"))
        header_payloads: list[dict[str, Any]] = []
        if self.vendor_header_pass and language in {"ar", "mixed"}:
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps

            with Image.open(image) as source:
                header = source.crop((0, 0, source.width, int(source.height * 0.42)))
                header = ImageOps.autocontrast(ImageOps.grayscale(header), cutoff=1)
                header = ImageEnhance.Contrast(header).enhance(1.15)
                header = header.filter(
                    ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=3)
                )
                header = header.resize(
                    (header.width * 2, header.height * 2),
                    Image.Resampling.LANCZOS,
                )
                header_path = image.with_name(f"{image.stem}_header.png")
                header.save(header_path, format="PNG", optimize=True)
            results = self.engines["ar"].predict(str(header_path))
            for result in results:
                data = result.json
                if isinstance(data, str):
                    data = json.loads(data)
                payload = data.get("res", data) if isinstance(data, dict) else {}
                header_payloads.append(payload)
        item_crop_lines: list[str] = []
        if self.item_crop_pass:
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps

            item_languages = ["ar", "en"] if language == "mixed" else ["ar"] if language == "ar" else ["en"]
            with Image.open(image) as source:
                items = source.crop(
                    (0, int(source.height * 0.34), source.width, int(source.height * 0.82))
                )
                items = ImageOps.autocontrast(ImageOps.grayscale(items), cutoff=1)
                items = ImageEnhance.Contrast(items).enhance(1.15)
                items = items.filter(
                    ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=3)
                )
                items = items.resize(
                    (items.width * 2, items.height * 2), Image.Resampling.LANCZOS
                )
                item_path = image.with_name(f"{image.stem}_items.png")
                items.save(item_path, format="PNG", optimize=True)
            for model_language in item_languages:
                for result in self.engines[model_language].predict(str(item_path)):
                    data = result.json
                    if isinstance(data, str):
                        data = json.loads(data)
                    payload = data.get("res", data) if isinstance(data, dict) else {}
                    item_crop_lines.extend(
                        self.ordered_texts(
                            payload, right_to_left=model_language == "ar"
                        )
                    )
        focused_crop_lines: list[str] = []
        if self.focused_fields_pass:
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps

            def prepare_focused_crop(box: tuple[int, int, int, int], name: str) -> Path:
                with Image.open(image) as source:
                    crop = source.crop(box)
                crop = ImageOps.autocontrast(ImageOps.grayscale(crop), cutoff=1)
                crop = ImageEnhance.Contrast(crop).enhance(1.2)
                crop = crop.filter(
                    ImageFilter.UnsharpMask(radius=1.2, percent=125, threshold=3)
                )
                crop = crop.resize(
                    (crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS
                )
                crop_path = image.with_name(f"{image.stem}_{name}.png")
                crop.save(crop_path, format="PNG", optimize=True)
                return crop_path

            with Image.open(image) as source:
                width, height = source.size
            if language in {"ar", "mixed"}:
                header_crop = prepare_focused_crop(
                    (0, 0, width, int(height * 0.34)), "arabic_header"
                )
                for result in self.engines["ar"].predict(str(header_crop)):
                    data = result.json
                    if isinstance(data, str):
                        data = json.loads(data)
                    payload = data.get("res", data) if isinstance(data, dict) else {}
                    focused_crop_lines.extend(
                        self.ordered_texts(payload, right_to_left=True)
                    )

                # RTL synthetic invoices place Arabic item descriptions in the
                # rightmost table column. Excluding quantity/price reduces
                # detector competition and gives small Arabic glyphs more pixels.
                description_crop = prepare_focused_crop(
                    (int(width * 0.56), int(height * 0.32), width, int(height * 0.64)),
                    "arabic_descriptions",
                )
                for result in self.engines["ar"].predict(str(description_crop)):
                    data = result.json
                    if isinstance(data, str):
                        data = json.loads(data)
                    payload = data.get("res", data) if isinstance(data, dict) else {}
                    focused_crop_lines.extend(
                        self.ordered_texts(payload, right_to_left=True)
                    )

            # Totals sit in the lower half of these invoice templates. A
            # separate enlarged crop gives currency digits a clean pass without
            # changing or replacing the full-page reading.
            amount_crop = prepare_focused_crop(
                (int(width * 0.48), int(height * 0.50), width, int(height * 0.80)),
                "amounts",
            )
            for result in self.engines["en"].predict(str(amount_crop)):
                data = result.json
                if isinstance(data, str):
                    data = json.loads(data)
                payload = data.get("res", data) if isinstance(data, dict) else {}
                focused_crop_lines.extend(
                    self.ordered_texts(payload, right_to_left=False)
                )
        if arabic_payloads:
            with Image.open(image) as source:
                page_height = source.height
            lines = self.merge_header_payloads(
                arabic_payloads,
                header_payloads,
                page_height=page_height,
            )
        else:
            lines = []
        lines.extend(other_lines)
        lines.extend(item_crop_lines)
        lines.extend(focused_crop_lines)
        elapsed = time.perf_counter() - start
        return "\n".join(lines), elapsed


def load_records(selected: str) -> list[tuple[str, Path, dict[str, Any]]]:
    records: list[tuple[str, Path, dict[str, Any]]] = []
    names = list(DATASETS) if selected == "all" else [selected]
    for name in names:
        folder = DATASETS[name]
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            # The original 50-invoice set keeps its manifest in the synthetic
            # parent directory; the later sets keep one beside their PDFs.
            manifest_path = folder.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in manifest["records"]:
            pdf = folder / row["file"]
            if not pdf.is_file():
                raise FileNotFoundError(pdf)
            records.append((name, pdf, row))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("tesseract", "paddleocr"), required=True)
    parser.add_argument("--set", dest="dataset", choices=("all", *DATASETS), default="all")
    parser.add_argument("--invoice-id", nargs="+", help="Run only the listed manifest invoice IDs")
    parser.add_argument("--output", type=Path, help="CSV destination; defaults to eval/results/<engine>_<set>.csv")
    parser.add_argument("--preprocess", choices=("raw", "enhance"), default="raw", help="Image input mode: original or grayscale/autocontrast/upscale/sharpen")
    parser.add_argument("--tesseract-psm", type=int, choices=(6, 11), default=6, help="Tesseract page segmentation: 6=uniform block, 11=sparse text")
    parser.add_argument("--no-paddle-vendor-header-pass", dest="paddle_vendor_header_pass", action="store_false", help="Disable the extra 2x Arabic OCR pass on the top 42%% of Arabic/mixed invoices")
    parser.add_argument("--paddle-item-crop-pass", action="store_true", help="Add an experimental 2x OCR pass on the middle/lower invoice region")
    parser.add_argument("--paddle-focused-fields-pass", action="store_true", help="Add separate enlarged PaddleOCR passes for the RTL Arabic item-description column and lower amount area")
    parser.set_defaults(paddle_vendor_header_pass=True)
    args = parser.parse_args()
    engine = TesseractEngine(args.tesseract_psm) if args.engine == "tesseract" else PaddleEngine(vendor_header_pass=args.paddle_vendor_header_pass, item_crop_pass=args.paddle_item_crop_pass, focused_fields_pass=args.paddle_focused_fields_pass)
    records = load_records(args.dataset)
    if args.invoice_id:
        selected_ids = set(args.invoice_id)
        records = [record for record in records if record[2]["id"] in selected_ids]
        missing_ids = selected_ids - {record[2]["id"] for record in records}
        if missing_ids:
            parser.error(f"Invoice IDs not found in selected set(s): {', '.join(sorted(missing_ids))}")
    output = args.output or ROOT / "eval" / "results" / f"ocr_{args.engine}_{args.dataset.replace('-', '_')}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for dataset, pdf, record in records:
        error = ""
        elapsed = 0.0
        preprocessing_elapsed = 0.0
        text = ""
        with tempfile.TemporaryDirectory(prefix="securefin-ocr-") as temp_name:
            try:
                raw_image = extract_image(pdf, Path(temp_name))
                preprocessing_start = time.perf_counter()
                image = preprocess_image(raw_image, args.preprocess)
                preprocessing_elapsed = time.perf_counter() - preprocessing_start
                text, elapsed = engine.recognize(image, str(record.get("language", "mixed")))
            except Exception as exc:  # keep the run going and record per-file failures
                error = f"{type(exc).__name__}: {exc}"
        expected = expected_fields(record)
        strict = {name: any(has_value(text, value, fold_arabic=False) for value in values) for name, values in expected.items()}
        normalized = {name: any(has_value(text, value, fold_arabic=True) for value in values) for name, values in expected.items()}
        line_items = record.get("line_items")
        line_count = len(line_items) if line_items is not None else None
        matched_line_items = sum(normalized.get(f"line_{index + 1}_description", False) for index in range(line_count or 0)) if line_items is not None else None
        rows.append({
            "engine": engine.name,
            "preprocessing": args.preprocess,
            "tesseract_psm": args.tesseract_psm if args.engine == "tesseract" else "",
            "paddle_vendor_header_pass": args.paddle_vendor_header_pass if args.engine == "paddleocr" else "",
            "paddle_item_crop_pass": args.paddle_item_crop_pass if args.engine == "paddleocr" else "",
            "paddle_focused_fields_pass": args.paddle_focused_fields_pass if args.engine == "paddleocr" else "",
            "dataset": dataset,
            "invoice_id": record["id"],
            "language": record.get("language", "unknown"),
            "quality_tier": record.get("quality_tier", "baseline"),
            "layout_variant": record.get("layout_variant", ""),
            "expected_line_items": line_count,
            "matched_line_items_by_description": matched_line_items,
            "line_item_count_hit": matched_line_items == line_count if line_count is not None else "",
            "expected_fields": len(expected),
            "strict_hits": sum(strict.values()),
            "strict_field_hit_rate": round(sum(strict.values()) / max(len(strict), 1), 4),
            "normalized_hits": sum(normalized.values()),
            "normalized_field_hit_rate": round(sum(normalized.values()) / max(len(normalized), 1), 4),
            "latency_seconds": round(elapsed, 4),
            "preprocessing_seconds": round(preprocessing_elapsed, 4),
            "total_seconds": round(elapsed + preprocessing_elapsed, 4),
            "recognized_text": text.replace("\r", "").strip(),
            "error": error,
            "field_details_json": json.dumps({name: {"expected": values, "strict_hit": strict[name], "normalized_hit": normalized[name]} for name, values in expected.items()}, ensure_ascii=False),
        })
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    avg = sum(row["normalized_field_hit_rate"] for row in rows) / max(len(rows), 1)
    failures = sum(bool(row["error"]) for row in rows)
    print(f"Processed {len(rows)} invoices with {engine.name}.")
    print(f"Mean normalized field hit rate: {avg:.1%}")
    print(f"Failed invoices: {failures}")
    print(f"Detailed per-invoice CSV: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
