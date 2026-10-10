"""Page-level Hebrew OCR with confidence and original-page bounding boxes."""

import csv
import io
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(arguments):
    result = subprocess.run(
        arguments,
        capture_output=True,
        timeout=120,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise ValueError("OCR_PROCESS_FAILED")
    return result.stdout.decode("utf-8")


def page_ocr(path, page_index, minimum_confidence=80):
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        raise ValueError("OCR_NOT_INSTALLED")
    with tempfile.TemporaryDirectory(prefix="pinui-ocr-") as directory:
        prefix = Path(directory) / "page"
        run(
            [
                "pdftoppm",
                "-f",
                str(page_index + 1),
                "-l",
                str(page_index + 1),
                "-singlefile",
                "-r",
                "300",
                "-png",
                str(path),
                str(prefix),
            ]
        )
        raw = run(["tesseract", str(prefix) + ".png", "stdout", "-l", "heb", "--psm", "3", "tsv"])
        lines = {}
        confidences = []
        for row in csv.DictReader(io.StringIO(raw), delimiter="\t"):
            if row["level"] != "5" or not row["text"].strip():
                continue
            confidence = float(row["conf"])
            confidences.append(confidence)
            key = tuple(row[k] for k in ("block_num", "par_num", "line_num"))
            lines.setdefault(key, []).append(row)
        average = sum(confidences) / len(confidences) if confidences else 0
        if average < minimum_confidence:
            raise ValueError("OCR_LOW_CONFIDENCE")
        text, geometry = "", []
        for rows in lines.values():
            line = " ".join(row["text"] for row in rows)
            if text:
                text += "\n"
            start = len(text)
            text += line
            left = min(int(r["left"]) for r in rows)
            top = min(int(r["top"]) for r in rows)
            right = max(int(r["left"]) + int(r["width"]) for r in rows)
            bottom = max(int(r["top"]) + int(r["height"]) for r in rows)
            # 300-DPI raster coordinates -> PDF points, top-left origin.
            geometry.append(
                {
                    "start": start,
                    "end": len(text),
                    "bbox": [v * 72 / 300 for v in (left, top, right, bottom)],
                }
            )
        return text, {
            "extraction_method": "ocr",
            "confidence": average,
            "geometry": geometry,
            "dpi": 300,
            "language": "heb",
        }


def attach_geometry(blocks, page_metadata):
    for block in blocks:
        locator = block["locator"]
        metadata = page_metadata.get(locator["pdf_page_index"])
        locator["extraction_method"] = "ocr" if metadata else "text_layer"
        if not metadata:
            continue
        boxes = [
            line["bbox"]
            for line in metadata["geometry"]
            if line["start"] < locator["page_char_end"] and line["end"] > locator["page_char_start"]
        ]
        if boxes:
            locator["bbox"] = [
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            ]
        locator["ocr_confidence"] = metadata["confidence"]
