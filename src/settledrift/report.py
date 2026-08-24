"""Builds the honest end-of-run report: match rate, per-class breakdown
(scored against ground truth when available), rupees reconciled, and the
exception list a human actually has to look at."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from settledrift.taxonomy import DriftClass


@dataclass
class ClassScore:
    predicted_count: int = 0
    true_count: int = 0
    correct: int = 0  # predicted == true AND true == this class

    @property
    def precision(self) -> float | None:
        return self.correct / self.predicted_count if self.predicted_count else None

    @property
    def recall(self) -> float | None:
        return self.correct / self.true_count if self.true_count else None


@dataclass
class Report:
    total_orders: int
    clean_exact: int
    clean_tolerance: int
    unresolved: int
    auto_resolved: int
    needs_review: int
    rupees_reconciled: float
    exceptions: list[dict]
    per_class: dict[str, ClassScore] = field(default_factory=dict)
    overall_accuracy: float | None = None

    def to_dict(self) -> dict:
        return {
            "total_orders": self.total_orders,
            "clean_exact": self.clean_exact,
            "clean_tolerance": self.clean_tolerance,
            "unresolved_by_matcher": self.unresolved,
            "agent_auto_resolved": self.auto_resolved,
            "agent_needs_review": self.needs_review,
            "match_rate": round(
                (self.clean_exact + self.clean_tolerance + self.auto_resolved) / self.total_orders, 4
            )
            if self.total_orders
            else None,
            "rupees_reconciled": round(self.rupees_reconciled, 2),
            "overall_classification_accuracy": self.overall_accuracy,
            "per_class": {
                cls: {
                    "predicted_count": s.predicted_count,
                    "true_count": s.true_count,
                    "correct": s.correct,
                    "precision": round(s.precision, 4) if s.precision is not None else None,
                    "recall": round(s.recall, 4) if s.recall is not None else None,
                }
                for cls, s in self.per_class.items()
            },
            "exception_count": len(self.exceptions),
            "exceptions": self.exceptions,
        }


def build_report(
    ledger: pd.DataFrame,
    settlement: pd.DataFrame,
    match_result,
    gate_decisions: list,
    ground_truth_path: Path | None = None,
) -> Report:
    total_orders = len(set(ledger["order_id"]) | set(settlement["order_id"]))

    rupees = 0.0
    for order_id in match_result.clean_order_ids:
        rows = ledger.loc[ledger["order_id"] == order_id]
        if len(rows) == 1:
            rupees += float(rows.iloc[0]["gross_amount"])

    predicted: dict[str, str] = {}
    # An exact match is a true CLEAN transaction. A tolerance match is the
    # matcher's own deterministic R1 call (sub-rupee gap) — it is NOT clean,
    # and mislabeling it CLEAN here would hide R1 from the class scoring.
    for oid in match_result.exact_order_ids:
        predicted[oid] = DriftClass.CLEAN.value
    for oid in match_result.tolerance_order_ids:
        predicted[oid] = DriftClass.R1.value
    exceptions = []
    for d in gate_decisions:
        predicted[d.order_id] = d.drift_class
        if d.status == "auto_resolved":
            rows = ledger.loc[ledger["order_id"] == d.order_id]
            if len(rows) == 1:
                rupees += float(rows.iloc[0]["gross_amount"])
        else:
            exceptions.append(
                {
                    "order_id": d.order_id,
                    "predicted_class": d.drift_class,
                    "confidence": d.confidence,
                    "reason": d.reason,
                }
            )

    auto_resolved = sum(1 for d in gate_decisions if d.status == "auto_resolved")
    needs_review = sum(1 for d in gate_decisions if d.status == "needs_review")

    per_class: dict[str, ClassScore] = {c.value: ClassScore() for c in DriftClass}
    overall_accuracy = None

    if ground_truth_path and ground_truth_path.exists():
        truth: dict[str, str] = {}
        with open(ground_truth_path) as f:
            for line in f:
                row = json.loads(line)
                truth[row["order_id"]] = row["class"]

        for oid, cls in predicted.items():
            per_class.setdefault(cls, ClassScore()).predicted_count += 1
        for oid, cls in truth.items():
            per_class.setdefault(cls, ClassScore()).true_count += 1

        correct_total = 0
        for oid, true_cls in truth.items():
            pred_cls = predicted.get(oid)
            if pred_cls == true_cls:
                per_class[true_cls].correct += 1
                correct_total += 1
        overall_accuracy = round(correct_total / len(truth), 4) if truth else None

    return Report(
        total_orders=total_orders,
        clean_exact=len(match_result.exact_order_ids),
        clean_tolerance=len(match_result.tolerance_order_ids),
        unresolved=len(match_result.unresolved_order_ids),
        auto_resolved=auto_resolved,
        needs_review=needs_review,
        rupees_reconciled=rupees,
        exceptions=exceptions,
        per_class=per_class,
        overall_accuracy=overall_accuracy,
    )
