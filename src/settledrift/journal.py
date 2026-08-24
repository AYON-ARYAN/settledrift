"""Append-only JSONL journal of every reconciliation decision. Mirrors
DriftBench's journal.py: one line per event, written once, never rewritten —
the run's audit trail."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a")

    def write(self, event: dict[str, Any]) -> None:
        self._fh.write(json.dumps(event) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def read_journal(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]
