"""The bounded investigation agent.

Every order_id the deterministic matcher couldn't resolve on its own gets
handed here. The agent sees only that order_id's evidence (never the ground
truth, never other merchants' data), may ask for one extra piece of context
(the customer's other orders — useful for spotting duplicates), and must
return a single classification into the R1-R6 taxonomy with a confidence
score and a one-line reason. It never writes to ledger.csv or settlement.csv;
the classification is data the confidence gate consumes downstream, not an
edit to the source records.
"""

from __future__ import annotations

from dataclasses import dataclass

from settledrift.agent.providers import ModelProvider, extract_json
from settledrift.agent.tools import Toolset
from settledrift.taxonomy import DESCRIPTIONS, DriftClass

SYSTEM_PROMPT = f"""You are a reconciliation investigator for an Indian payments merchant.
You classify one order at a time into exactly one drift class:

{chr(10).join(f"- {c.value}: {d}" for c, d in DESCRIPTIONS.items() if c != DriftClass.CLEAN)}

The evidence you receive is already precomputed — trust these fields directly,
do not recompute them yourself:
- ledger_row_count / settlement_row_count: how many rows exist on each side.
- diff_rupees_expected_vs_actual: only set when both counts are exactly 1.
- settlement_lag_days: only set when both counts are exactly 1.

Decision order — check in this order and stop at the first match:
1. If ledger_row_count == 0 or settlement_row_count == 0 -> R6 (no counterpart at all).
2. If ledger_row_count >= 2 -> R5 (duplicate booking on the ledger side).
3. If settlement_row_count >= 2 -> R4 (split payout).
4. If a ledger row's status is "partially_refunded" -> R3.
5. If diff_rupees_expected_vs_actual <= 0.5 AND settlement_lag_days > 2 -> R2 (amount is fine, it just arrived late).
6. If diff_rupees_expected_vs_actual > 0.5 -> if settlement_lag_days > 2 it is still R2, not R1 — R1 is ONLY for
   sub-rupee/rounding-sized gaps. A gap in the tens or hundreds of rupees is never R1.
7. Otherwise -> R1.

You may ask for one extra piece of evidence before answering by responding with
exactly: {{"tool": "get_customer_orders", "customer": "<name>"}}
Only do this if you need to see the customer's other orders to confirm a duplicate.
Otherwise skip straight to the final answer.

When ready, respond with ONLY a JSON object, no prose, no markdown fences:
{{"class": "R1"|"R2"|"R3"|"R4"|"R5"|"R6", "confidence": 0.0-1.0, "reasoning": "<one line>"}}
"""


@dataclass
class Classification:
    order_id: str
    drift_class: str
    confidence: float
    reasoning: str
    tool_calls: int = 0
    fallback: bool = False


def _rule_based_fallback(order_id: str, evidence: dict) -> Classification:
    """Deterministic backstop if the model output isn't parseable JSON, so a
    flaky local model can never silently drop an order from the report."""
    ledger_rows = evidence["ledger_rows"]
    settlement_rows = evidence["settlement_rows"]
    if len(ledger_rows) == 0 or len(settlement_rows) == 0:
        cls = DriftClass.R6
    elif len(ledger_rows) >= 2:
        cls = DriftClass.R5
    elif len(settlement_rows) >= 2:
        cls = DriftClass.R4
    elif ledger_rows[0].get("status") == "partially_refunded":
        cls = DriftClass.R3
    else:
        cls = DriftClass.R2
    return Classification(
        order_id=order_id,
        drift_class=cls.value,
        confidence=0.3,
        reasoning="rule-based fallback: model output unparseable",
        fallback=True,
    )


def investigate_order(
    order_id: str,
    toolset: Toolset,
    provider: ModelProvider,
    max_tool_calls: int = 1,
) -> Classification:
    evidence = toolset.evidence_bundle(order_id)
    user_prompt = f"Evidence for order_id={order_id}:\n{evidence}"

    tool_calls = 0
    for _ in range(max_tool_calls + 1):
        response = provider.complete(SYSTEM_PROMPT, user_prompt)
        try:
            parsed = extract_json(response.text)
        except Exception:
            return _rule_based_fallback(order_id, evidence)

        if "tool" in parsed and tool_calls < max_tool_calls:
            tool_calls += 1
            if parsed["tool"] == "get_customer_orders":
                customer = parsed.get("customer", "")
                orders = toolset.get_customer_orders(customer)
                user_prompt += (
                    f"\n\nTool result for get_customer_orders({customer!r}): {orders}"
                    "\nNow give your final answer as JSON only."
                )
                continue

        if "class" in parsed:
            drift_class = str(parsed["class"]).strip().upper()
            if drift_class not in {c.value for c in DriftClass if c != DriftClass.CLEAN}:
                return _rule_based_fallback(order_id, evidence)
            confidence = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            return Classification(
                order_id=order_id,
                drift_class=drift_class,
                confidence=confidence,
                reasoning=str(parsed.get("reasoning", "")),
                tool_calls=tool_calls,
            )

        return _rule_based_fallback(order_id, evidence)

    return _rule_based_fallback(order_id, evidence)
