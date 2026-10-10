"""Read-only PDF and hash validation for C01, using the existing host pypdf."""

import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "data/corpus-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    for row in manifest["documents"]:
        if row["download_status"] != "downloaded":
            continue
        try:
            pdf = ROOT / row["file"]
            if hashlib.sha256(pdf.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("SHA-256 mismatch")
            reader = PdfReader(pdf)
            if reader.is_encrypted or not len(reader.pages):
                raise ValueError("PDF is encrypted or has no pages")
            # Access every page object; sample text only. Full extraction/OCR is T03.
            for page in reader.pages:
                if float(page.mediabox.width) <= 0 or float(page.mediabox.height) <= 0:
                    raise ValueError("Invalid page geometry")
            text = "\n".join(page.extract_text() or "" for page in reader.pages[:3])
            row["pdf_validation"] = {
                "status": "passed",
                "pages": len(reader.pages),
                "sample_text_characters": len(text),
                "sample_hebrew_characters": len(re.findall(r"[\u0590-\u05ff]", text)),
                "text_sample": text[:1800],
                "ocr_review_required": len(re.findall(r"[\u0590-\u05ff]", text)) < 20,
            }
        except Exception as exc:
            failures.append(row["download_id"])
            row["pdf_validation"] = {"status": "failed", "error": str(exc)}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    good = [
        d for d in manifest["documents"] if d.get("pdf_validation", {}).get("status") == "passed"
    ]
    print(f"PDF/hash checks: {len(good)} passed, {len(failures)} failed")
    print(f"Pages: {sum(d['pdf_validation']['pages'] for d in good)}")
    print(f"OCR review: {sum(d['pdf_validation']['ocr_review_required'] for d in good)}")
    if failures:
        print("Failed IDs:", ", ".join(failures))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
