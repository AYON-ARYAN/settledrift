"""Recomputes what the confidence gate would have decided at other
thresholds, purely from an already-completed run's journal.jsonl — no new
LLM calls. Every agent-classified order's confidence and correctness (when
ground truth is available) was already recorded once; this just re-applies
gate.py's threshold rule to that recorded data at each candidate threshold.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from settledrift.taxonomy import NEVER_AUTO_RESOLVABLE, DriftClass


@dataclass
class ThresholdPoint:
    threshold: float
    auto_resolved: int
    needs_review: int
    wrong_among_auto_resolved: int  # correctness leak: agent was wrong but still auto-resolved
    total_agent_calls: int

    @property
    def automation_rate(self) -> float:
        return self.auto_resolved / self.total_agent_calls if self.total_agent_calls else 0.0

    @property
    def error_leak_rate(self) -> float:
        """Fraction of AUTO-RESOLVED decisions that were actually wrong —
        the number that matters for trust, not raw accuracy."""
        return self.wrong_among_auto_resolved / self.auto_resolved if self.auto_resolved else 0.0


def sweep_thresholds(
    journal_path: Path,
    ground_truth_path: Path | None,
    thresholds: list[float] | None = None,
) -> list[ThresholdPoint]:
    thresholds = thresholds or [0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 0.95, 1.0]

    truth: dict[str, str] = {}
    if ground_truth_path and ground_truth_path.exists():
        with open(ground_truth_path) as f:
            for line in f:
                row = json.loads(line)
                truth[row["order_id"]] = row["class"]

    investigated = []
    with open(journal_path) as f:
        for line in f:
            row = json.loads(line)
            if row.get("event") == "investigated":
                investigated.append(row)

    points = []
    for threshold in thresholds:
        auto = 0
        review = 0
        wrong_auto = 0
        for row in investigated:
            cls = DriftClass(row["predicted_class"])
            is_r6 = cls in NEVER_AUTO_RESOLVABLE
            would_auto = (
                not is_r6
                and not row.get("fallback", False)
                and row["confidence"] >= threshold
            )
            if would_auto:
                auto += 1
                if truth.get(row["order_id"]) and truth[row["order_id"]] != row["predicted_class"]:
                    wrong_auto += 1
            else:
                review += 1
        points.append(
            ThresholdPoint(
                threshold=threshold,
                auto_resolved=auto,
                needs_review=review,
                wrong_among_auto_resolved=wrong_auto,
                total_agent_calls=len(investigated),
            )
        )
    return points


def format_sweep_table(points: list[ThresholdPoint]) -> str:
    header = f"{'threshold':>9} | {'auto':>5} | {'review':>6} | {'automation %':>12} | {'wrong-but-auto':>14}"
    lines = [header, "-" * len(header)]
    for p in points:
        lines.append(
            f"{p.threshold:>9.2f} | {p.auto_resolved:>5} | {p.needs_review:>6} | "
            f"{p.automation_rate * 100:>11.1f}% | {p.wrong_among_auto_resolved:>14}"
        )
    return "\n".join(lines)
