import time

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

import settledrift.web.jobs as jobs_module
from settledrift.agent.providers import ModelResponse
from settledrift.web.app import app


class StubProvider:
    """Always classifies as R6 with high confidence — deterministic and fast,
    so these tests don't depend on Ollama being installed or running."""

    def complete(self, system: str, user: str) -> ModelResponse:
        return ModelResponse(text='{"class": "R6", "confidence": 0.99, "reasoning": "stub"}')


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs_module, "parse_provider", lambda spec: StubProvider())
    monkeypatch.setattr(jobs_module, "RUNS_ROOT", tmp_path / "runs_web")
    return TestClient(app)


def _wait_for_job(job_id: str, timeout: float = 30.0) -> jobs_module.Job:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs_module.get_job(job_id)
        if job and job.status in ("done", "error"):
            return job
        time.sleep(0.1)
    raise TimeoutError(f"job {job_id} did not finish in {timeout}s")


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SettleDrift" in resp.text


def test_rejects_out_of_range_n(client):
    resp = client.post("/api/run", json={"n": 5, "seed": 1, "provider": "ollama:x", "threshold": 0.75})
    assert resp.status_code == 400


def test_rejects_out_of_range_threshold(client):
    resp = client.post("/api/run", json={"n": 60, "seed": 1, "provider": "ollama:x", "threshold": 2.0})
    assert resp.status_code == 400


def test_full_run_completes_and_serves_all_artifacts(client):
    resp = client.post("/api/run", json={"n": 30, "seed": 5, "provider": "ollama:x", "threshold": 0.75})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = _wait_for_job(job_id)
    assert job.status == "done"
    assert job.report is not None

    report_resp = client.get(f"/api/report/{job_id}")
    assert report_resp.status_code == 200
    assert report_resp.json()["total_orders"] == 30

    dash_resp = client.get(f"/dashboard/{job_id}")
    assert dash_resp.status_code == 200
    assert "<!doctype html>" in dash_resp.text

    csv_resp = client.get(f"/api/exceptions/{job_id}.csv")
    assert csv_resp.status_code == 200


def test_unknown_job_id_returns_404(client):
    assert client.get("/api/report/does-not-exist").status_code == 404
    assert client.get("/dashboard/does-not-exist").status_code == 404
    assert client.get("/api/exceptions/does-not-exist.csv").status_code == 404
