"""Wires deterministic matcher -> agent investigation -> confidence gate ->
journal -> report into one run. This is the module the CLI's `reconcile`
command calls."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from settledrift.agent.investigate import investigate_order
from settledrift.agent.providers import ModelProvider
from settledrift.agent.tools import Toolset
from settledrift.gate import GateDecision, apply_gate
from settledrift.journal import Journal
from settledrift.matcher import FEE_TOLERANCE, LAG_TOLERANCE_DAYS, deterministic_match
from settledrift.report import Report, build_report


def _deterministic_r3(order_id: str, toolset: Toolset) -> GateDecision | None:
    """A partial refund is a fact already recorded on the ledger's own status
    column — asking an LLM to (mis)infer it from amounts is both wasteful and,
    per an earlier real run, actively unreliable. Resolve it directly."""
    ledger_rows = toolset.get_ledger_rows(order_id)
    settlement_rows = toolset.get_settlement_rows(order_id)
    if len(ledger_rows) != 1 or len(settlement_rows) != 1:
        return None
    if ledger_rows[0].get("status") != "partially_refunded":
        return None
    return GateDecision(
        order_id=order_id,
        drift_class="R3",
        confidence=1.0,
        status="auto_resolved",
        reason="deterministic: ledger status == partially_refunded",
    )


def _deterministic_r2(order_id: str, toolset: Toolset) -> GateDecision | None:
    """Same reasoning as _deterministic_r3: whether the amount is within
    tolerance and whether the settlement lagged are both arithmetic the
    matcher already does with certainty (see matcher.deterministic_match) —
    a real pilot run showed the local model unreliably confusing this with
    R1 even when handed the precomputed lag, so resolve it directly instead
    of gambling on the model reading a number correctly."""
    evidence = toolset.evidence_bundle(order_id)
    diff = evidence["diff_rupees_expected_vs_actual"]
    lag = evidence["settlement_lag_days"]
    if diff is None or lag is None:
        return None
    if diff <= FEE_TOLERANCE and lag > LAG_TOLERANCE_DAYS:
        return GateDecision(
            order_id=order_id,
            drift_class="R2",
            confidence=1.0,
            status="auto_resolved",
            reason=f"deterministic: diff {diff:.2f} within tolerance, lag {lag}d > {LAG_TOLERANCE_DAYS}d",
        )
    return None


def run_reconciliation(
    ledger_path: Path,
    settlement_path: Path,
    journal_path: Path,
    provider: ModelProvider,
    ground_truth_path: Path | None = None,
    confidence_threshold: float = 0.75,
    progress=None,
) -> Report:
    ledger = pd.read_csv(ledger_path)
    settlement = pd.read_csv(settlement_path)

    match_result = deterministic_match(ledger, settlement)
    toolset = Toolset(ledger=ledger, settlement=settlement)

    gate_decisions = []
    with Journal(journal_path) as journal:
        journal.write({
            "event": "run_start",
            "ledger_path": str(ledger_path),
            "settlement_path": str(settlement_path),
            "unresolved_count": len(match_result.unresolved_order_ids),
        })

        for order_id in sorted(match_result.exact_order_ids):
            journal.write({"event": "clean_match", "order_id": order_id, "kind": "exact"})
        for order_id in sorted(match_result.tolerance_order_ids):
            journal.write({"event": "clean_match", "order_id": order_id, "kind": "tolerance"})

        unresolved = sorted(match_result.unresolved_order_ids)
        for i, order_id in enumerate(unresolved):
            t0 = time.time()

            deterministic_decision = _deterministic_r3(order_id, toolset) or _deterministic_r2(order_id, toolset)
            if deterministic_decision is not None:
                gate_decisions.append(deterministic_decision)
                journal.write({
                    "event": "deterministic_resolved",
                    "order_id": order_id,
                    "predicted_class": deterministic_decision.drift_class,
                    "gate_status": deterministic_decision.status,
                    "gate_reason": deterministic_decision.reason,
                    "elapsed_s": round(time.time() - t0, 2),
                })
                if progress:
                    progress(i + 1, len(unresolved), order_id, deterministic_decision)
                continue

            classification = investigate_order(order_id, toolset, provider)
            decision = apply_gate(classification, threshold=confidence_threshold)
            gate_decisions.append(decision)
            journal.write({
                "event": "investigated",
                "order_id": order_id,
                "predicted_class": classification.drift_class,
                "confidence": classification.confidence,
                "reasoning": classification.reasoning,
                "tool_calls": classification.tool_calls,
                "fallback": classification.fallback,
                "gate_status": decision.status,
                "gate_reason": decision.reason,
                "elapsed_s": round(time.time() - t0, 2),
            })
            if progress:
                progress(i + 1, len(unresolved), order_id, decision)

        journal.write({"event": "run_end"})

    return build_report(ledger, settlement, match_result, gate_decisions, ground_truth_path)
