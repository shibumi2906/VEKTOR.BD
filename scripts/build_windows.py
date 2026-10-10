"""Assemble an offline bundle from verified, prepared Windows runtime inputs."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "data/windows-build"
BUNDLE = BUILD / "bundle"


def copy(source, target):
    if source.is_dir():
        shutil.copytree(
            source,
            target,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main():
    BUNDLE.mkdir(parents=True, exist_ok=True)
    for directory in ("app", "ui", "config", "scripts", "migrations", "packaging/windows"):
        copy(ROOT / directory, BUNDLE / directory)
    copy(ROOT / "alembic.ini", BUNDLE / "alembic.ini")
    copy(BUILD / "python-managed/cpython-3.12.15-windows-x86_64-none", BUNDLE / "python")
    copy(
        ROOT / "packaging/windows/offline_guard.py",
        BUNDLE / "python/Lib/site-packages/sitecustomize.py",
    )
    for directory in ("bin", "lib", "share"):
        copy(BUILD / "postgres/pgsql" / directory, BUNDLE / "postgres" / directory)
    copy(BUILD / "qdrant", BUNDLE / "qdrant")
    copy(BUILD / "poppler/poppler-26.09.0", BUNDLE / "poppler")
    copy(BUILD / "ocr", BUNDLE / "ocr")
    for runtime in (BUILD / "vc-runtime").glob("*.dll"):
        for target in ("python", "postgres/bin", "qdrant"):
            copy(runtime, BUNDLE / target / runtime.name)
    copy(BUILD / "runtime-licenses/Microsoft-Runtime", BUNDLE / "licenses/Microsoft-Runtime")
    manifest = json.loads((ROOT / "data/index-manifest.json").read_text(encoding="utf-8"))
    for model in (manifest["model"], manifest["reranker"]):
        copy(ROOT / "data/models" / model["name"], BUNDLE / "models" / model["name"])
    copy(ROOT / "data/models/manifest.json", BUNDLE / "models/manifest.json")
    copy(BUILD / "desktop-config.json", BUNDLE / "desktop-config.json")
    for name in ("raw.tar.gz", "pipeline.tar.gz", "vectors.jsonl.gz", "vectors-config.json"):
        copy(BUILD / "seed-export" / name, BUNDLE / "seed" / name)
    copy(ROOT / "data/index-manifest.json", BUNDLE / "seed/index-manifest.json")
    copy(BUILD / "postgres.dump", BUNDLE / "seed/postgres.dump")
    copy(ROOT / "packaging/windows/README-ru.txt", BUNDLE / "README-ru.txt")
    copy(ROOT / "packaging/windows/THIRD-PARTY-NOTICES.txt", BUNDLE / "THIRD-PARTY-NOTICES.txt")
    compiler = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
    subprocess.run(
        [
            str(compiler),
            "/nologo",
            "/target:winexe",
            "/reference:System.Windows.Forms.dll",
            "/out:" + str(BUNDLE / "PinuiRAG.exe"),
            str(ROOT / "packaging/windows/Launcher.cs"),
        ],
        check=True,
    )
    forbidden = [
        p
        for p in BUNDLE.rglob("*")
        if p.name in {".env", "openai-key.json", "postgres-password.txt"}
    ]
    if forbidden:
        raise RuntimeError("A secret file was found in the package")
    provenance = {}
    for name in (
        "postgresql-direct.zip",
        "qdrant.zip",
        "tesseract.exe",
        "heb.traineddata",
        "poppler.zip",
        "vc-redist.exe",
        "inno.exe",
        "7zip.exe",
        "7zr.exe",
    ):
        path = BUILD / "downloads" / name
        with path.open("rb") as source:
            provenance[name] = hashlib.file_digest(source, "sha256").hexdigest()
    (BUNDLE / "component-download-hashes.json").write_text(json.dumps(provenance, indent=2))
    report = {
        "documents": 18,
        "chunks": manifest["chunks"],
        "secret_files": 0,
        "files": sum(p.is_file() for p in BUNDLE.rglob("*")),
        "bytes": sum(p.stat().st_size for p in BUNDLE.rglob("*") if p.is_file()),
    }
    (BUILD / "bundle-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
