"""Local private contract import; immutable originals never enter Git or logs."""

import asyncio
import hashlib
import json
import shutil
from pathlib import Path

from app.config.settings import Settings
from app.parsing.registered import parse_registered
from app.registry.corpus import identity
from app.services.database import connect


async def main():
    settings = Settings()
    connection = await connect(settings)
    project = identity("project:local-contracts")
    results = []
    try:
        await connection.execute(
            (
                "INSERT INTO registry.projects VALUES($1,'local-contract"
                "s','Договоры',now()) ON CONFLICT DO NOTHING"
            ),
            project,
        )
        await connection.execute(
            "INSERT INTO registry.source_registry VALUES('private-lo"
            "cal','manual','Локальные договоры',86400,'{}',now()) ON"
            " CONFLICT DO NOTHING"
        )
        for path in sorted(Path("договора").glob("*")):
            if path.suffix.lower() not in (".pdf", ".docx"):
                continue
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            family = identity("private-family:" + path.stem)
            document = identity("private-document:" + path.stem + ":" + sha)
            key = "private/" + sha + path.suffix.lower()
            target = settings.raw_storage_path / key
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(path, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
                raise ValueError("Stored original mismatch")
            async with connection.transaction():
                await connection.execute(
                    (
                        "INSERT INTO registry.document_families(family_id,slug,t"
                        "itle,project_id) VALUES($1,$2,$3,$4) ON CONFLICT DO NOT"
                        "HING"
                    ),
                    family,
                    path.stem,
                    "Договор " + path.stem,
                    project,
                )
                await connection.execute(
                    (
                        "INSERT INTO registry.document_versions\n                "
                        "    (document_id,family_id,title,title_he,document_type"
                        ",category,language,\n                    version_label,d"
                        "ocument_role,version_status,legal_status,verification_s"
                        "tatus,\n                    source_id,source_url,source_"
                        "name,issuer,raw_file_key,file_sha256,size_bytes,page_co"
                        "unt,metadata)\n                    VALUES($1,$2,$3,$3,$4"
                        ",'contract','he',$5,$6,'unknown','not_applicable',\n    "
                        "                'manual_review','private-local','','Лок"
                        "альный файл','Не подтверждён',$7,$8,$9,NULL,'{}')\n     "
                        "               ON CONFLICT DO NOTHING"
                    ),
                    document,
                    family,
                    "Договор " + path.stem,
                    path.suffix[1:].lower(),
                    path.stem,
                    "draft_contract" if path.suffix.lower() == ".docx" else "contract",
                    key,
                    sha,
                    path.stat().st_size,
                )
            results.append(await parse_registered(connection, settings, document))
        Path("data/private-parse-report.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "private_documents": len(results),
                    "blocks": sum(r["blocks"] for r in results),
                    "chunks": sum(r["chunks"] for r in results),
                }
            ),
            flush=True,
        )
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
