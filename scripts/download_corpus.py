"""C01: download an explicitly curated official PDF corpus, without indexing it."""

import argparse
import concurrent.futures
import hashlib
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.registry.policy import validate_current_policy  # noqa: E402

MAX_BYTES = 50 * 1024 * 1024
HOST_PATHS = {
    "fs.knesset.gov.il": ("/",),
    "www.gov.il": ("/BlobFolder/",),
    "www.minhelet-holon.co.il": (
        "/wp-content/uploads/2022/08/",
        "/wp-content/uploads/2022/06/",
        "/wp-content/uploads/2022/01/",
        "/wp-content/uploads/2019/09/",
    ),
    "cramim-pt.co.il": ("/wp-content/uploads/2023/03/",),
    "minhelet-j.org.il": ("/wp-content/uploads/2025/06/",),
    "www.nzc.org.il": ("/uploads/n/1728989690.3437.pdf",),
    "www.minheletyavne.org.il": ("/html5/Web/8295/doc557.pdf",),
}


def validate_url(url, resolve=True):
    parsed = urllib.parse.urlsplit(url)
    path = urllib.parse.unquote(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOST_PATHS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or "\\" in path
        or ".." in path.split("/")
        or not path.lower().endswith(".pdf")
        or not any(path.startswith(p) for p in HOST_PATHS.get(parsed.hostname, ()))
    ):
        raise ValueError("URL is outside the curated official PDF allowlist")
    if (
        parsed.hostname in ("www.nzc.org.il", "www.minheletyavne.org.il")
        and path not in HOST_PATHS[parsed.hostname]
    ):
        raise ValueError("Only the explicitly curated municipal PDF is allowed")
    if parsed.hostname == "fs.knesset.gov.il" and not re.fullmatch(
        r"/\d+/law/\d+_(?:lsr(?:_ec)?|ls_fr)_\d+\.pdf", path, re.IGNORECASE
    ):
        raise ValueError("Only gazette law PDFs are allowed; bills are excluded")
    if resolve:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("Official host resolved to a non-public address")
    return url


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_pdf(url):
    validate_url(url)
    opener = urllib.request.build_opener(CheckedRedirect())
    with opener.open(url, timeout=45) as response:
        validate_url(response.url)
        if int(response.headers.get("Content-Length", "0")) > MAX_BYTES:
            raise ValueError("PDF exceeds the download size limit")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or not data.startswith(b"%PDF-") or b"%%EOF" not in data[-4096:]:
            raise ValueError("Response is not a complete PDF within the size limit")
        return (
            data,
            response.url,
            response.headers.get("ETag"),
            response.headers.get("Last-Modified"),
        )


def acquire(document):
    row = dict(document)
    row.update(
        downloaded_at=datetime.now(UTC).isoformat(),
        language="he",
        document_role="official",
        version_status="unknown",
        legal_status="unknown",
        verification_status="manual_review",
        publication_date=None,
        effective_from=None,
        effective_to=None,
        indexed=False,
        current_norms_eligible=False,
    )
    if not re.fullmatch(r"[a-z0-9_]+", row["download_id"]):
        raise ValueError("Unsafe download_id")
    for attempt in range(3):
        try:
            data, final_url, etag, modified = fetch_pdf(row["url"])
            digest = hashlib.sha256(data).hexdigest()
            relative = Path("data/raw/legislation") / f"{row['download_id']}_{digest[:16]}.pdf"
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise ValueError("Existing immutable original has a conflicting hash")
            else:
                with target.open("xb") as output:
                    output.write(data)
            row.update(
                download_status="downloaded",
                file=relative.as_posix(),
                sha256=digest,
                size_bytes=len(data),
                final_url=final_url,
                etag=etag,
                last_modified=modified,
            )
            row.pop("error", None)
            print(f"OK {row['download_id']} {len(data)} bytes", flush=True)
            return row
        except (OSError, ValueError, urllib.error.URLError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403, 404):
                break
            if attempt < 2:
                time.sleep(attempt + 1)
    row["download_status"] = "failed"
    row["verification_status"] = "failed"
    print(f"FAIL {row['download_id']}: {row['error']}", flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 5))
    parser.add_argument("--refresh", action="store_true", help="Re-fetch existing URLs")
    args = parser.parse_args()
    config = json.loads((ROOT / "config/corpus-downloads.json").read_text(encoding="utf-8"))
    validate_current_policy(config)
    manifest_path = ROOT / "data/corpus-manifest.json"
    previous = {}
    previous_manifest = {}
    if manifest_path.exists() and not args.refresh:
        previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous = {row["url"]: row for row in previous_manifest["documents"]}

    def acquire_or_reuse(document):
        old = previous.get(document["url"])
        if old:
            if old["download_status"] == "failed":
                if old.get("error", "").startswith("ValueError:"):
                    validate_url(document["url"], resolve=False)
                    return acquire(document)
                return {**old, **document}
            path = ROOT / old["file"]
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == old["sha256"]:
                return {**old, **document}
        return acquire(document)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        documents = list(pool.map(acquire_or_reuse, config["documents"]))
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "legal_verification_complete": False,
        "index_created": False,
        "documents": documents,
        "required_documents_not_acquired": config.get("required_documents_not_acquired", []),
        "baseline_law_families": [
            family["family_alias"]
            for family in config.get("families", [])
            if family["family_alias"] not in ("standard21", "meeting_summary")
        ],
    }
    manifest["retention_policy"] = config.get("retention_policy", "historical_publications")
    for field in ("source_checks", "cleanup"):
        if field in previous_manifest:
            manifest[field] = previous_manifest[field]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = sum(row["download_status"] != "downloaded" for row in documents)
    print(f"Downloaded {len(documents) - failed}/{len(documents)}; manifest: {manifest_path}")
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
