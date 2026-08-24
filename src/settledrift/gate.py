"""Confidence gate: turns an agent classification into an accept/review
decision. R6 is hard-coded to always need human review — there is no amount
of model confidence that manufactures a counterpart that doesn't exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from settledrift.agent.investigate import Classification
from settledrift.taxonomy import NEVER_AUTO_RESOLVABLE, DriftClass

DEFAULT_THRESHOLD = 0.75


@dataclass
class GateDecision:
    order_id: str
    drift_class: str
    confidence: float
    status: str  # "auto_resolved" | "needs_review"
    reason: str


def apply_gate(classification: Classification, threshold: float = DEFAULT_THRESHOLD) -> GateDecision:
    cls = DriftClass(classification.drift_class)

    if cls in NEVER_AUTO_RESOLVABLE:
        return GateDecision(
            order_id=classification.order_id,
            drift_class=classification.drift_class,
            confidence=classification.confidence,
            status="needs_review",
            reason=f"{cls.value} is never auto-resolvable",
        )

    if classification.fallback:
        return GateDecision(
            order_id=classification.order_id,
            drift_class=classification.drift_class,
            confidence=classification.confidence,
            status="needs_review",
            reason="rule-based fallback output, not model-confirmed",
        )

    if classification.confidence >= threshold:
        return GateDecision(
            order_id=classification.order_id,
            drift_class=classification.drift_class,
            confidence=classification.confidence,
            status="auto_resolved",
            reason=f"confidence {classification.confidence:.2f} >= threshold {threshold:.2f}",
        )

    return GateDecision(
        order_id=classification.order_id,
        drift_class=classification.drift_class,
        confidence=classification.confidence,
        status="needs_review",
        reason=f"confidence {classification.confidence:.2f} < threshold {threshold:.2f}",
    )
