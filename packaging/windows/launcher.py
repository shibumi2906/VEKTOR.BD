"""Offline Windows launcher. All executables are resolved inside the installed bundle."""

import argparse
import gzip
import json
import msvcrt
import os
import queue
import secrets
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import webbrowser
from pathlib import Path

import httpx
import win32api
import win32job

BUNDLE = Path(__file__).resolve().parents[2]
PYTHON = BUNDLE / "python/python.exe"
HIDDEN = subprocess.CREATE_NO_WINDOW


class AlreadyRunning(Exception):
    pass


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_http(url, process, timeout=120):
    end = time.monotonic() + timeout
    with httpx.Client(trust_env=False, timeout=2) as client:
        while time.monotonic() < end:
            if process.poll() is not None:
                raise RuntimeError("Компонент приложения завершился при запуске.")
            try:
                response = client.get(url)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.4)
    raise RuntimeError("Компонент приложения не успел запуститься. Смотрите папку logs.")


class Application:
    def __init__(self, data, messages):
        self.data, self.messages = data, messages
        self.processes = []
        self.logs = []
        self.job = win32job.CreateJobObject(None, "")
        limits = win32job.QueryInformationJobObject(
            self.job, win32job.JobObjectExtendedLimitInformation
        )
        limits["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(
            self.job, win32job.JobObjectExtendedLimitInformation, limits
        )
        self.runtime = data / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        (data / "logs").mkdir(exist_ok=True)
        self.stop_event = threading.Event()
        self.owns_lock = False
        self.failed = False

    def spawn(self, name, args, env=None):
        output = (self.data / "logs" / (name + ".log")).open("ab")
        self.logs.append(output)
        child = subprocess.Popen(
            args, cwd=BUNDLE, env=env, stdout=output, stderr=output, creationflags=HIDDEN
        )
        try:
            win32job.AssignProcessToJobObject(self.job, int(child._handle))
        except Exception:
            child.terminate()
            raise RuntimeError("Не удалось настроить завершение фоновых компонентов.") from None
        self.processes.append(child)
        return child

    def command(self, args, env=None):
        result = subprocess.run(
            args, cwd=BUNDLE, env=env, capture_output=True, creationflags=HIDDEN, timeout=180
        )
        if result.returncode:
            # Command output may include a local credential: do not display/log it.
            raise RuntimeError("Не удалось подготовить локальную базу данных.")

    def start(self):
        self.lock = (self.runtime / "instance.lock").open("a+b")
        self.lock.seek(0)
        try:
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            self.owns_lock = True
        except OSError:
            previous = json.loads((self.runtime / "session.json").read_text())
            webbrowser.open(previous["ui_url"])
            raise AlreadyRunning from None
        for name in ("stop.request", "ready.json", "failure.json"):
            (self.runtime / name).unlink(missing_ok=True)
        self.messages.put("Подготовка документов и моделей…")
        seed = BUNDLE / "seed"
        original_dir = self.data / "raw"
        if not (self.data / "seed-files.ready").exists():
            original_dir.mkdir(exist_ok=True)
            with tarfile.open(seed / "raw.tar.gz") as archive:
                archive.extractall(original_dir, filter="data")
            index_dir = self.data / "index"
            index_dir.mkdir(exist_ok=True)
            shutil.copy2(seed / "index-manifest.json", index_dir / "index-manifest.json")
            with tarfile.open(seed / "pipeline.tar.gz") as archive:
                archive.extractall(index_dir, filter="data")
            (self.data / "seed-files.ready").touch()
        ports = {name: free_port() for name in ("pg", "qdrant", "api", "ui")}
        pg = BUNDLE / "postgres/bin"
        pgdata = self.data / "postgres"
        self.pgdata = pgdata
        credential_path = self.runtime / "postgres-password.txt"
        if not credential_path.exists():
            credential_path.write_text(secrets.token_hex(32), encoding="ascii")
        password = credential_path.read_text(encoding="ascii").strip()
        env = os.environ.copy()
        # Neither a system Python/Docker nor an online model cache is needed.
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        env.update(
            {
                "PATH": os.pathsep.join(
                    [
                        str(pg),
                        str(BUNDLE / "ocr"),
                        str(BUNDLE / "poppler/Library/bin"),
                        str(BUNDLE / "python"),
                        str(Path(os.environ["SystemRoot"]) / "System32"),
                    ]
                ),
                "PGPASSWORD": password,
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "TESSDATA_PREFIX": str(BUNDLE / "ocr/tessdata"),
            }
        )
        self.env = env
        self.messages.put("Запуск базы документов…")
        if not (pgdata / "PG_VERSION").exists():
            self.command(
                [
                    str(pg / "initdb.exe"),
                    "-D",
                    str(pgdata),
                    "-U",
                    "pinui",
                    "-E",
                    "UTF8",
                    "--locale=C",
                    "--auth=scram-sha-256",
                    "--pwfile=" + str(credential_path),
                ],
                env,
            )
        pgprocess = self.spawn(
            "postgres",
            [
                str(pg / "postgres.exe"),
                "-D",
                str(pgdata),
                "-p",
                str(ports["pg"]),
                "-h",
                "127.0.0.1",
            ],
            env,
        )
        end = time.monotonic() + 60
        pgargs = ["-h", "127.0.0.1", "-p", str(ports["pg"]), "-U", "pinui"]
        while time.monotonic() < end:
            probe = subprocess.run(
                [str(pg / "pg_isready.exe"), *pgargs],
                env=env,
                capture_output=True,
                creationflags=HIDDEN,
            )
            if probe.returncode == 0:
                break
            if pgprocess.poll() is not None:
                raise RuntimeError("Не запустилась локальная база документов.")
            time.sleep(0.4)
        else:
            raise RuntimeError("База документов не успела запуститься.")
        if not (self.data / "postgres.ready").exists():
            # createdb may already have succeeded during a previously interrupted first launch.
            subprocess.run(
                [str(pg / "createdb.exe"), *pgargs, "pinui"],
                env=env,
                capture_output=True,
                creationflags=HIDDEN,
            )
            self.command(
                [
                    str(pg / "pg_restore.exe"),
                    *pgargs,
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                    "-d",
                    "pinui",
                    str(seed / "postgres.dump"),
                ],
                env,
            )
            (self.data / "postgres.ready").touch()
        self.messages.put("Запуск векторной базы…")
        vector_config = {
            "telemetry_disabled": True,
            "storage": {
                "storage_path": str(self.data / "qdrant"),
                "snapshots_path": str(self.data / "snapshots"),
            },
            "service": {
                "host": "127.0.0.1",
                "http_port": ports["qdrant"],
                "grpc_port": None,
                "enable_cors": False,
            },
            "cluster": {"enabled": False},
        }
        config_path = self.runtime / "qdrant.yaml"
        config_path.write_text(json.dumps(vector_config), encoding="utf-8")
        vector = self.spawn(
            "qdrant", [str(BUNDLE / "qdrant/qdrant.exe"), "--config-path", str(config_path)], env
        )
        qurl = f"http://127.0.0.1:{ports['qdrant']}"
        wait_http(qurl + "/readyz", vector)
        if not (self.data / "qdrant.ready").exists():
            manifest = json.loads((seed / "index-manifest.json").read_text())
            config = json.loads((seed / "vectors-config.json").read_text())
            collection_url = qurl + "/collections/" + manifest["collection"]
            with httpx.Client(trust_env=False, timeout=180) as client:
                # An interrupted import can be resumed by idempotent point upserts.
                if client.get(collection_url).status_code == 404:
                    client.put(collection_url, json=config).raise_for_status()
                with gzip.open(seed / "vectors.jsonl.gz", "rt", encoding="utf-8") as vectors:
                    batch = []
                    for line in vectors:
                        batch.append(json.loads(line))
                        if len(batch) == 128:
                            client.put(
                                collection_url + "/points?wait=true", json={"points": batch}
                            ).raise_for_status()
                            batch = []
                    if batch:
                        client.put(
                            collection_url + "/points?wait=true", json={"points": batch}
                        ).raise_for_status()
                count = client.post(collection_url + "/points/count", json={"exact": True}).json()[
                    "result"
                ]["count"]
                if count != manifest["chunks"]:
                    raise RuntimeError("Не удалось полностью восстановить векторную базу.")
            (self.data / "qdrant.ready").touch()
        configuration = json.loads((BUNDLE / "desktop-config.json").read_text())
        env.update(
            {
                key.upper(): json.dumps(value) if isinstance(value, list) else str(value)
                for key, value in configuration.items()
            }
        )
        env.update(
            {
                "POSTGRES_URL": f"postgresql://pinui:{password}@127.0.0.1:{ports['pg']}/pinui",
                "QDRANT_URL": qurl,
                "RUNTIME_PATH": str(self.runtime),
                "RAW_STORAGE_PATH": str(original_dir),
                "MODEL_STORAGE_PATH": str(BUNDLE / "models"),
                "INDEX_STORAGE_PATH": str(self.data / "index"),
                "OPENAI_API_KEY": "",
                "QDRANT_API_KEY": "",
                "ADMIN_API_TOKEN": "",
                "READER_API_TOKEN": "",
                "API_BASE_URL": f"http://127.0.0.1:{ports['api']}",
            }
        )
        self.messages.put("Загрузка локальных моделей поиска…")
        for role in ("worker", "scheduler"):
            self.spawn(role, [str(PYTHON), "-m", "app.jobs.process", role], env)
        api = self.spawn(
            "api",
            [
                str(PYTHON),
                "-m",
                "uvicorn",
                "app.api.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports["api"]),
            ],
            env,
        )
        wait_http(env["API_BASE_URL"] + "/status", api, 180)
        self.messages.put("Открытие интерфейса…")
        ui = self.spawn(
            "ui",
            [
                str(PYTHON),
                "-m",
                "streamlit",
                "run",
                "ui/main.py",
                "--server.address=127.0.0.1",
                "--server.port=" + str(ports["ui"]),
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
            ],
            env,
        )
        ui_url = f"http://127.0.0.1:{ports['ui']}"
        wait_http(ui_url + "/_stcore/health", ui)
        session = {
            "ui_url": ui_url,
            "api_url": env["API_BASE_URL"],
            "ports": ports,
            "python": str(PYTHON),
            "bundle": str(BUNDLE),
            "pids": [p.pid for p in self.processes],
        }
        for name in ("session.json", "ready.json"):
            (self.runtime / name).write_text(json.dumps(session), encoding="utf-8")
        self.messages.put("Готово. Интерфейс открыт в браузере.")
        return ui_url

    def close(self):
        self.stop_event.set()
        if hasattr(self, "pgdata"):
            subprocess.run(
                [
                    str(BUNDLE / "postgres/bin/pg_ctl.exe"),
                    "-D",
                    str(self.pgdata),
                    "-m",
                    "fast",
                    "-w",
                    "-t",
                    "15",
                    "stop",
                ],
                capture_output=True,
                creationflags=HIDDEN,
                timeout=20,
            )
        win32api.CloseHandle(self.job)
        for output in self.logs:
            output.close()
        if self.owns_lock:
            (self.runtime / "ready.json").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    data = args.data_dir or Path(os.environ["LOCALAPPDATA"]) / "PinuiRAG/data"
    messages = queue.Queue()
    app = Application(data, messages)

    def run():
        try:
            url = app.start()
            if not args.no_browser:
                webbrowser.open(url)
            while not app.stop_event.wait(0.5):
                if (app.runtime / "stop.request").exists():
                    break
                if any(p.poll() is not None for p in app.processes):
                    raise RuntimeError("Один из компонентов завершился. Перезапустите приложение.")
        except AlreadyRunning:
            pass
        except Exception as error:
            app.failed = True
            # Never display arbitrary upstream errors or command lines with credentials.
            message = (
                str(error)
                if isinstance(error, RuntimeError)
                else "Ошибка запуска. Смотрите папку logs."
            )
            messages.put(message)
            (app.runtime / "failure.json").write_text(
                json.dumps({"message": message}), encoding="utf-8"
            )
        finally:
            app.close()

    if args.headless:
        run()
        return
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("PinuiRAG")
    root.geometry("490x175")
    root.resizable(False, False)
    label = ttk.Label(root, text="Запуск приложения…", wraplength=450)
    label.pack(padx=20, pady=22)

    def stop():
        if worker.is_alive():
            label.configure(text="Завершение приложения…")
            app.stop_event.set()
        else:
            root.destroy()

    button = ttk.Button(root, text="Закрыть приложение", command=stop)
    button.pack(pady=8)
    root.protocol("WM_DELETE_WINDOW", stop)
    worker = threading.Thread(target=run)
    worker.start()

    def refresh():
        while not messages.empty():
            label.configure(text=messages.get_nowait())
        if not worker.is_alive() and app.stop_event.is_set() and not app.failed:
            root.destroy()
        else:
            root.after(200, refresh)

    root.after(200, refresh)
    root.mainloop()


if __name__ == "__main__":
    main()
