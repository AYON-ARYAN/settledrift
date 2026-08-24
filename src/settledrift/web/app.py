"""FastAPI app for the local web UI. Thin wrapper over the same pipeline the
CLI calls — see jobs.py. Run with `settledrift serve`."""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from settledrift.web.jobs import get_job, start_job
from settledrift.web.templates import INDEX_HTML

app = FastAPI(title="SettleDrift")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.post("/api/run")
async def api_run(payload: dict) -> dict:
    n = int(payload.get("n", 120))
    seed = int(payload.get("seed", 42))
    provider = str(payload.get("provider", "ollama:qwen2.5-coder:3b"))
    threshold = float(payload.get("threshold", 0.75))

    if not (10 <= n <= 2000):
        raise HTTPException(400, "n must be between 10 and 2000")
    if not (0.0 <= threshold <= 1.0):
        raise HTTPException(400, "threshold must be between 0 and 1")

    job = start_job(n=n, seed=seed, provider_spec=provider, threshold=threshold)
    return {"job_id": job.id}


@app.get("/api/stream/{job_id}")
async def api_stream(job_id: str) -> StreamingResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "unknown job_id")

    async def event_source():
        loop = asyncio.get_event_loop()
        while True:
            event = await loop.run_in_executor(None, job.events.get)
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "close":
                break

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.get("/api/report/{job_id}")
async def api_report(job_id: str) -> JSONResponse:
    job = get_job(job_id)
    if job is None or job.report is None:
        raise HTTPException(404, "report not ready")
    return JSONResponse(job.report)


@app.get("/api/exceptions/{job_id}.csv")
async def api_exceptions(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "unknown job_id")
    path = job.out_dir / "exceptions.csv"
    if not path.exists():
        raise HTTPException(404, "exceptions.csv not ready")
    return FileResponse(path, media_type="text/csv", filename="exceptions.csv")


@app.get("/dashboard/{job_id}", response_class=HTMLResponse)
async def dashboard_view(job_id: str) -> str:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "unknown job_id")
    path = job.out_dir / "dashboard.html"
    if not path.exists():
        raise HTTPException(404, "dashboard not ready")
    return path.read_text()
