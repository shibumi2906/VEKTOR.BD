import hashlib
from pathlib import Path

import pytest

from scripts import download_corpus as corpus


@pytest.mark.parametrize(
    "url",
    [
        "http://fs.knesset.gov.il/16/law/16_lsr_299902.pdf",
        "https://fs.knesset.gov.il.evil.example/16/law/16_lsr_299902.pdf",
        "https://user:secret@fs.knesset.gov.il/16/law/16_lsr_299902.pdf",
        "https://fs.knesset.gov.il/16/law/16_ls1_299902.pdf",
        "https://www.gov.il/BlobFolder/../private.pdf",
        "https://www.gov.il/BlobFolder/test.pdf?token=secret",
        "https://127.0.0.1/BlobFolder/test.pdf",
        "https://www.gov.il/maintenance-page-geo",
        "https://www.minhelet-holon.co.il/wp-content/uploads/2023/standard.pdf",
        "https://www.minhelet-holon.co.il.evil.example/wp-content/uploads/2022/08/standard.pdf",
        "https://cramim-pt.co.il/wp-content/uploads/2024/03/contract.pdf",
        "https://www.nzc.org.il/uploads/n/other.pdf",
        "https://www.nzc.org.il/uploads/n/1728989690.3437.pdf/other.pdf",
    ],
)
def test_untrusted_or_non_enacted_download_is_rejected(url):
    with pytest.raises(ValueError):
        corpus.validate_url(url, resolve=False)


def test_official_url_cannot_resolve_to_private_address(monkeypatch):
    monkeypatch.setattr(
        corpus.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.1", 443))]
    )
    with pytest.raises(ValueError, match="non-public"):
        corpus.validate_url("https://fs.knesset.gov.il/16/law/16_lsr_299902.pdf")


def test_curated_standard_archive_url_is_accepted():
    url = "https://www.minhelet-holon.co.il/wp-content/uploads/2022/08/%D7%AA%D7%A7%D7%9F-21.1.pdf"
    assert corpus.validate_url(url, resolve=False) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://cramim-pt.co.il/wp-content/uploads/2023/03/contract.pdf",
        "https://minhelet-j.org.il/wp-content/uploads/2025/06/regulation.pdf",
        "https://www.nzc.org.il/uploads/n/1728989690.3437.pdf",
        "https://www.minhelet-holon.co.il/wp-content/uploads/2022/06/regulation.pdf",
    ],
)
def test_curated_municipal_pdf_paths_are_accepted(url):
    assert corpus.validate_url(url, resolve=False) == url


def test_changed_source_preserves_both_originals_without_legal_activation(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "ROOT", tmp_path)
    document = {
        "download_id": "test_law",
        "url": "https://fs.knesset.gov.il/16/law/16_lsr_299902.pdf",
    }
    versions = iter([b"%PDF-1.4\noriginal\n%%EOF", b"%PDF-1.4\namended\n%%EOF"])
    monkeypatch.setattr(corpus, "fetch_pdf", lambda url: (next(versions), url, None, None))
    first = corpus.acquire(document)
    second = corpus.acquire(document)
    assert first["file"] != second["file"]
    for row in (first, second):
        file = tmp_path / Path(row["file"])
        assert hashlib.sha256(file.read_bytes()).hexdigest() == row["sha256"]
        assert row["verification_status"] == "manual_review"
        assert row["legal_status"] == "unknown"
        assert row["effective_from"] is None
        assert not row["indexed"]
