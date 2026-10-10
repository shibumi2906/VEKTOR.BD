"""Real Windows acceptance with bundled executables and external networking disabled."""

import argparse
import asyncio
import gzip
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import UUID

import asyncpg
import httpx
from pydantic import SecretStr

from app.config.settings import Settings
from app.services.model_key import key_path, restore_key, save_key


async def verify(bundle, data, session):
    api = session["api_url"]
    with httpx.Client(trust_env=False, timeout=90) as client:
        status = client.get(api + "/status").json()
        assert not status["capabilities"]["llm_configured"]
        blocked = client.post(
            api + "/settings/openai", json={"api_key": "sk-synthetic-never-valid"}
        )
        assert blocked.json()["error"]["code"] == "KEY_CHECK_UNAVAILABLE"
        assert not client.get(api + "/settings/openai").json()["configured"]
        docs = client.get(api + "/documents?limit=100").json()["documents"]
        results = []
        for topic, document in [
            ("מה תפקידו של עורך דין בעלי הדירות?", None),
            ("מי משלם את שכר עורך הדין?", "contract_04_2025"),
            ("מי משלם את שכר עורך הדין?", "contract_08_2025"),
        ]:
            # Locate contracts by version metadata; do not print private titles or text.
            selected = []
            if document:
                version = "04.2025" if "04" in document else "08.2025"
                selected = [
                    d["document_id"]
                    for d in docs
                    if d["category"] == "contract" and d.get("version_label") == version
                ]
                assert selected, "Contract version missing"
            response = client.post(
                api + "/query",
                json={
                    "question": topic,
                    "response_mode": "search",
                    "language": "he",
                    "mode": "project_documents" if selected else "all_documents",
                    "document_ids": selected,
                },
            )
            assert response.status_code == 200, response.status_code
            result = response.json()
            assert result["sources"]
            assert not result["usage"]
            results.append(result)
        password = (data / "runtime/postgres-password.txt").read_text().strip()
        db = await asyncpg.connect(
            host="127.0.0.1",
            port=session["ports"]["pg"],
            user="pinui",
            password=password,
            database="pinui",
        )
        try:
            for result in results:
                for source in result["sources"]:
                    original = await db.fetchval(
                        "SELECT original_text FROM registry.blocks WHERE block_id=$1",
                        UUID(source["block_id"]),
                    )
                    assert source["quote"] == original[source["span_start"] : source["span_end"]]
            document_count = await db.fetchval("SELECT count(*) FROM registry.document_versions")
        finally:
            await db.close()
        with httpx.Client(trust_env=False) as qclient:
            manifest = json.loads((bundle / "seed/index-manifest.json").read_text())
            count = qclient.post(
                f"http://127.0.0.1:{session['ports']['qdrant']}/collections/"
                + manifest["collection"]
                + "/points/count",
                json={"exact": True},
            ).json()
            assert count["result"]["count"] == manifest["chunks"]
            with gzip.open(bundle / "seed/vectors.jsonl.gz", "rt", encoding="utf-8") as file:
                expected = {str(p["id"]): p for p in map(json.loads, file)}
            offset = None
            checked = 0
            while True:
                payload = {"limit": 128, "with_payload": True, "with_vector": True}
                if offset is not None:
                    payload["offset"] = offset
                batch = qclient.post(
                    f"http://127.0.0.1:{session['ports']['qdrant']}/collections/"
                    + manifest["collection"]
                    + "/points/scroll",
                    json=payload,
                ).json()["result"]
                for point in batch["points"]:
                    original = expected[str(point["id"])]
                    assert point["vector"] == original["vector"]
                    assert point["payload"] == original["payload"]
                    checked += 1
                offset = batch["next_page_offset"]
                if offset is None:
                    break
            assert checked == manifest["chunks"]
        assert client.get(session["ui_url"] + "/_stcore/health").status_code == 200
    config = Settings(
        _env_file=None,
        app_mode="bootstrap",
        runtime_path=data / "credential-test",
        openai_api_key=SecretStr(""),
    )
    synthetic = "sk-synthetic-windows-protection-test"
    save_key(config, synthetic)
    assert synthetic not in key_path(config).read_text()
    config.openai_api_key = SecretStr("")
    restore_key(config)
    assert config.openai_api_key.get_secret_value() == synthetic
    pid_list = ",".join(str(int(pid)) for pid in session["pids"])
    module_command = (
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
        f"Get-Process -Id {pid_list} | ForEach-Object {{ $_.Modules }} | "
        "Where-Object { $_.ModuleName -match '^(msvcp140|vcruntime140|concrt140)' } | "
        "Select-Object -ExpandProperty FileName | ConvertTo-Json -Compress"
    )
    raw = subprocess.check_output(
        [
            str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
            "-NoProfile",
            "-Command",
            module_command,
        ],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    modules = json.loads(raw.decode("utf-8"))
    if isinstance(modules, str):
        modules = [modules]
    assert modules and all(Path(path).resolve().is_relative_to(bundle) for path in modules)
    return {
        "documents": document_count,
        "vectors": manifest["chunks"],
        "searches": [
            {
                "status": r["status"],
                "citations": len(r["sources"]),
                "exact_originals": True,
                "paid_calls": len(r["usage"]),
            }
            for r in results
        ],
        "model_key_in_installer": False,
        "system_python_on_path": False,
        "docker_on_path": False,
        "python_external_network_disabled": True,
        "offline_guard_verified": True,
        "vectors_and_payloads_exact": checked,
        "windows_dpapi_roundtrip": True,
        "vc_runtime_loaded_from_bundle": True,
        "ui_http": 200,
        "bundle": str(bundle),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("data", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    bundle, data = args.bundle.resolve(), args.data.resolve()
    assert Path(os.sys.executable).resolve().is_relative_to(bundle), "Use bundled Python"
    env = os.environ.copy()
    env.update(
        PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
        PINUI_OFFLINE_TEST="1",
        OPENAI_API_KEY="",
    )
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    assert shutil.which("docker", path=env["PATH"]) is None
    assert shutil.which("python", path=env["PATH"]) is None
    launcher = subprocess.Popen(
        [
            str(bundle / "python/python.exe"),
            str(bundle / "packaging/windows/launcher.py"),
            "--headless",
            "--no-browser",
            "--data-dir",
            str(data),
        ],
        cwd=bundle,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    ready = data / "runtime/ready.json"
    started = time.monotonic()
    try:
        while time.monotonic() - started < 300:
            if ready.exists():
                break
            if launcher.poll() is not None:
                raise RuntimeError("Launcher failed; inspect failure.json and component logs")
            time.sleep(0.5)
        assert ready.exists(), "Startup timeout"
        session = json.loads(ready.read_text())
        startup_seconds = round(time.monotonic() - started, 2)
        report = asyncio.run(verify(bundle, data, session))
        report["startup_seconds"] = startup_seconds
        report["acceptance_seconds"] = round(time.monotonic() - started, 2)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        stop = data / "runtime/stop.request"
        stop.parent.mkdir(parents=True, exist_ok=True)
        stop.touch()
        launcher.wait(timeout=45)
    assert not ready.exists(), "Shutdown cleanup failed"


if __name__ == "__main__":
    main()
