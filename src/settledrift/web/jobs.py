"""In-memory job manager for the web UI. Each 'run' is a background thread
executing the same run_reconciliation() the CLI calls — the web layer adds
no new pipeline logic, only a queue for streaming its existing progress
callback out over SSE."""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from settledrift.agent.providers import parse_provider
from settledrift.dashboard import write_dashboard
from settledrift.data.generate import generate
from settledrift.exceptions_export import write_exceptions_csv
from settledrift.journal import read_journal
from settledrift.pipeline import run_reconciliation

RUNS_ROOT = Path("runs/web")


@dataclass
class Job:
    id: str
    status: str = "queued"  # queued -> generating -> running -> done -> error
    events: "queue.Queue[dict]" = field(default_factory=queue.Queue)
    report: dict | None = None
    error: str | None = None
    data_dir: Path = field(default_factory=Path)
    out_dir: Path = field(default_factory=Path)
    started_at: float = field(default_factory=time.time)


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def get_job(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def _emit(job: Job, **event: Any) -> None:
    job.events.put(event)


def _run_job(job: Job, n: int, seed: int, provider_spec: str, threshold: float) -> None:
    try:
        job.status = "generating"
        _emit(job, type="status", status="generating", detail=f"Generating {n} synthetic transactions (seed={seed})")
        generate(job.data_dir, n=n, seed=seed)

        job.status = "running"
        _emit(job, type="status", status="running", detail=f"Reconciling with provider={provider_spec}")

        provider = parse_provider(provider_spec)

        def progress(i: int, total: int, order_id: str, decision) -> None:
            _emit(
                job,
                type="progress",
                current=i,
                total=total,
                order_id=order_id,
                drift_class=decision.drift_class,
                gate_status=decision.status,
                confidence=decision.confidence,
            )

        job.out_dir.mkdir(parents=True, exist_ok=True)
        report = run_reconciliation(
            ledger_path=job.data_dir / "ledger.csv",
            settlement_path=job.data_dir / "settlement.csv",
            journal_path=job.out_dir / "journal.jsonl",
            provider=provider,
            ground_truth_path=job.data_dir / "ground_truth.jsonl",
            confidence_threshold=threshold,
            progress=progress,
        )
        report_dict = report.to_dict()
        (job.out_dir / "report.json").write_text(json.dumps(report_dict, indent=2))

        journal_rows = read_journal(job.out_dir / "journal.jsonl")
        write_dashboard(report_dict, journal_rows, job.out_dir / "dashboard.html", title=f"SettleDrift · run {job.id[:8]}")
        write_exceptions_csv(report_dict, job.out_dir / "exceptions.csv")

        job.report = report_dict
        job.status = "done"
        _emit(job, type="status", status="done", detail="Run complete")
    except Exception as exc:  # a failed run must surface, never hang the UI forever
        job.status = "error"
        job.error = str(exc)
        _emit(job, type="status", status="error", detail=str(exc))
    finally:
        _emit(job, type="close")


def start_job(n: int, seed: int, provider_spec: str, threshold: float) -> Job:
    job_id = uuid.uuid4().hex
    job = Job(
        id=job_id,
        data_dir=RUNS_ROOT / job_id / "data",
        out_dir=RUNS_ROOT / job_id / "out",
    )
    with _LOCK:
        _JOBS[job_id] = job

    thread = threading.Thread(target=_run_job, args=(job, n, seed, provider_spec, threshold), daemon=True)
    thread.start()
    return job
