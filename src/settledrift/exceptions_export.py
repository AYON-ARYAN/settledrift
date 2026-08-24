"""Exports the exception list as CSV — what a finance controller actually
hands to a human reviewer, not a JSON blob buried in report.json."""

from __future__ import annotations

import csv
from pathlib import Path


FIELDNAMES = ["order_id", "predicted_class", "confidence", "reason"]


def write_exceptions_csv(report: dict, path: Path) -> int:
    exceptions = report.get("exceptions", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for e in exceptions:
            writer.writerow({k: e[k] for k in FIELDNAMES})
    return len(exceptions)
