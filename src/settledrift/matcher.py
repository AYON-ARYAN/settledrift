"""Deterministic matcher: resolves the confident majority with zero LLM calls.

An order_id present exactly once on each side, whose settled_amount is within
FEE_TOLERANCE of the ledger's gross_amount minus the expected fee+tax, is a
CLEAN match. Everything else — duplicates, splits, missing counterparts,
amounts outside tolerance — is left for the candidate grouper and the agent.
This mirrors DriftBench's principle of never asking a model to do what a
deterministic check already answers with certainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

FEE_RATE = 0.02
GST_RATE = 0.18
FEE_TOLERANCE = 0.5  # rupees; a diff this small is a rounding artifact (R1), not an error
LAG_TOLERANCE_DAYS = 2  # a same/next-day-ish settlement; longer gaps need investigating as R2


def expected_net(gross: float) -> float:
    fee = round(gross * FEE_RATE, 2)
    tax = round(fee * GST_RATE, 2)
    return round(gross - fee - tax, 2)


@dataclass
class MatchResult:
    exact_order_ids: set[str] = field(default_factory=set)
    tolerance_order_ids: set[str] = field(default_factory=set)  # matched, but had a rounding-sized gap
    unresolved_order_ids: set[str] = field(default_factory=set)

    @property
    def clean_order_ids(self) -> set[str]:
        return self.exact_order_ids | self.tolerance_order_ids


def deterministic_match(ledger: pd.DataFrame, settlement: pd.DataFrame) -> MatchResult:
    result = MatchResult()

    ledger_counts = ledger["order_id"].value_counts()
    settlement_counts = settlement["order_id"].value_counts()

    all_order_ids = set(ledger["order_id"]) | set(settlement["order_id"])

    for order_id in all_order_ids:
        l_count = int(ledger_counts.get(order_id, 0))
        s_count = int(settlement_counts.get(order_id, 0))

        # Anything other than exactly-one-on-each-side needs investigation:
        # 0 on either side is a missing counterpart, 2+ is a duplicate/split.
        if l_count != 1 or s_count != 1:
            result.unresolved_order_ids.add(order_id)
            continue

        ledger_row = ledger.loc[ledger["order_id"] == order_id].iloc[0]
        settlement_row = settlement.loc[settlement["order_id"] == order_id].iloc[0]

        expected = expected_net(float(ledger_row["gross_amount"]))
        actual = float(settlement_row["settled_amount"])

        diff = abs(expected - actual)
        lag_days = (
            pd.Timestamp(settlement_row["settlement_date"]) - pd.Timestamp(ledger_row["order_date"])
        ).days

        if diff > FEE_TOLERANCE:
            result.unresolved_order_ids.add(order_id)
        elif lag_days > LAG_TOLERANCE_DAYS:
            # Amount checks out, but it took too long to land — that's R2's
            # signature, not a clean match, regardless of how small diff is.
            result.unresolved_order_ids.add(order_id)
        elif diff == 0:
            result.exact_order_ids.add(order_id)
        else:
            result.tolerance_order_ids.add(order_id)

    return result
