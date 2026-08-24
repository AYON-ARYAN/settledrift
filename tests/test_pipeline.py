import pandas as pd

from settledrift.agent.tools import Toolset
from settledrift.pipeline import _deterministic_r2, _deterministic_r3


def test_partially_refunded_status_resolves_to_r3_without_calling_the_model():
    ledger = pd.DataFrame(
        [{"order_id": "o1", "customer": "C", "order_date": "2026-07-01",
          "gross_amount": 1000.0, "status": "partially_refunded"}]
    )
    settlement = pd.DataFrame(
        [{"payment_id": "p1", "order_id": "o1", "settled_amount": 400.0, "fee": 8.0,
          "tax": 1.44, "settlement_date": "2026-07-02", "utr": "U1"}]
    )
    toolset = Toolset(ledger=ledger, settlement=settlement)
    decision = _deterministic_r3("o1", toolset)
    assert decision is not None
    assert decision.drift_class == "R3"
    assert decision.status == "auto_resolved"
    assert decision.confidence == 1.0


def test_non_refunded_status_returns_none_and_falls_through_to_agent():
    ledger = pd.DataFrame(
        [{"order_id": "o1", "customer": "C", "order_date": "2026-07-01",
          "gross_amount": 1000.0, "status": "paid"}]
    )
    settlement = pd.DataFrame(
        [{"payment_id": "p1", "order_id": "o1", "settled_amount": 976.4, "fee": 20.0,
          "tax": 3.6, "settlement_date": "2026-07-10", "utr": "U1"}]
    )
    toolset = Toolset(ledger=ledger, settlement=settlement)
    assert _deterministic_r3("o1", toolset) is None
    # this evidence (diff~0, lag=9d) is exactly the R2 shortcut's shape
    assert _deterministic_r2("o1", toolset) is not None


def test_amount_matches_and_lag_within_tolerance_is_not_r2():
    ledger = pd.DataFrame(
        [{"order_id": "o1", "customer": "C", "order_date": "2026-07-01",
          "gross_amount": 1000.0, "status": "paid"}]
    )
    settlement = pd.DataFrame(
        [{"payment_id": "p1", "order_id": "o1", "settled_amount": 976.4, "fee": 20.0,
          "tax": 3.6, "settlement_date": "2026-07-02", "utr": "U1"}]
    )
    toolset = Toolset(ledger=ledger, settlement=settlement)
    assert _deterministic_r2("o1", toolset) is None


def test_refunded_status_with_mismatched_row_counts_defers_to_agent():
    # A refund note that landed on a split payout shouldn't be silently
    # forced through the R3 shortcut — that's genuinely ambiguous.
    ledger = pd.DataFrame(
        [{"order_id": "o1", "customer": "C", "order_date": "2026-07-01",
          "gross_amount": 1000.0, "status": "partially_refunded"}]
    )
    settlement = pd.DataFrame(
        [
            {"payment_id": "p1", "order_id": "o1", "settled_amount": 200.0, "fee": 4.0,
             "tax": 0.72, "settlement_date": "2026-07-02", "utr": "U1"},
            {"payment_id": "p2", "order_id": "o1", "settled_amount": 200.0, "fee": 4.0,
             "tax": 0.72, "settlement_date": "2026-07-05", "utr": "U2"},
        ]
    )
    toolset = Toolset(ledger=ledger, settlement=settlement)
    assert _deterministic_r3("o1", toolset) is None
