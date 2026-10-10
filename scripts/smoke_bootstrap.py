"""HTTP smoke checks for running T01 services; never calls a model provider."""

import json
import os
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

api = f"http://127.0.0.1:{os.environ.get('API_PORT', '8010')}"
ui = f"http://127.0.0.1:{os.environ.get('UI_PORT', '8510')}"


def fetch(url):
    with urlopen(url, timeout=10) as response:
        return response.status, response.read(), response.headers


last_failure = "services not ready"
for _ in range(20):
    try:
        code, data, _ = fetch(api + "/health")
        assert code == 200 and json.loads(data)["status"] == "alive"
        code, data, headers = fetch(api + "/status")
        body = json.loads(data)
        assert code == 200 and body["status"] == "ready"
        assert body["scope"] == "bootstrap_infrastructure"
        assert body["request_id"] == headers["X-Request-ID"]
        assert not any(
            body["capabilities"][name]
            for name in ("search_he", "translation", "answer_generation", "topic_comparison")
        )
        assert body["capabilities"]["llm_configured"] is False
        assert all(
            body["components"][name]["status"] == "ready"
            for name in ("postgres", "qdrant", "worker_process", "scheduler_process")
        )
        assert body["components"]["job_processing"]["status"] == "not_implemented"
        assert fetch(ui + "/_stcore/health")[0] == 200
        assert fetch(ui)[0] == 200
        try:
            fetch(api + "/api/v1/query")
        except HTTPError as error:
            assert error.code == 404
            assert json.loads(error.read())["error"]["code"] == "NOT_FOUND"
        else:
            raise AssertionError("Query endpoint must not masquerade as implemented")
        print("PASS: API health/readiness, PostgreSQL/Qdrant/processes, UI and no-key capabilities")
        break
    except (URLError, HTTPException, OSError, AssertionError, KeyError, ValueError) as error:
        last_failure = type(error).__name__
        time.sleep(2)
else:
    raise SystemExit(f"Smoke check failed: {last_failure}")
