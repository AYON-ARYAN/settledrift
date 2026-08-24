from __future__ import annotations

import json
from pathlib import Path

import typer

from settledrift.agent.providers import parse_provider
from settledrift.data.generate import generate
from settledrift.pipeline import run_reconciliation

app = typer.Typer(add_completion=False)


@app.command()
def gen(
    out_dir: Path = typer.Option(Path("runs/data"), "--out", help="Output directory"),
    n: int = typer.Option(120, "--n", help="Number of base transactions"),
    seed: int = typer.Option(42, "--seed"),
):
    """Generate a synthetic ledger + settlement + ground truth corpus."""
    generate(out_dir, n=n, seed=seed)
    typer.echo(f"Generated {n} transactions under {out_dir}")


@app.command()
def reconcile(
    data_dir: Path = typer.Option(Path("runs/data"), "--data", help="Directory with ledger.csv/settlement.csv"),
    out_dir: Path = typer.Option(Path("runs/out"), "--out", help="Where to write journal.jsonl and report.json"),
    provider: str = typer.Option("ollama:qwen2.5-coder:3b", "--provider"),
    threshold: float = typer.Option(0.75, "--threshold"),
    use_ground_truth: bool = typer.Option(True, "--use-ground-truth/--no-ground-truth"),
):
    """Run the full pipeline: deterministic match -> agent -> gate -> report."""
    out_dir.mkdir(parents=True, exist_ok=True)
    model_provider = parse_provider(provider)
    gt_path = data_dir / "ground_truth.jsonl" if use_ground_truth else None

    def progress(i, total, order_id, decision):
        typer.echo(f"[{i}/{total}] {order_id} -> {decision.drift_class} ({decision.status}, conf={decision.confidence:.2f})")

    report = run_reconciliation(
        ledger_path=data_dir / "ledger.csv",
        settlement_path=data_dir / "settlement.csv",
        journal_path=out_dir / "journal.jsonl",
        provider=model_provider,
        ground_truth_path=gt_path,
        confidence_threshold=threshold,
        progress=progress,
    )

    report_dict = report.to_dict()
    with open(out_dir / "report.json", "w") as f:
        json.dump(report_dict, f, indent=2)

    typer.echo(json.dumps(report_dict, indent=2))


@app.command()
def report(out_dir: Path = typer.Option(Path("runs/out"), "--out")):
    """Print a previously generated report.json."""
    path = out_dir / "report.json"
    if not path.exists():
        typer.echo(f"No report at {path}. Run `settledrift reconcile` first.", err=True)
        raise typer.Exit(1)
    typer.echo(path.read_text())


if __name__ == "__main__":
    app()
