import pandas as pd

from settledrift.matcher import MatchResult
from settledrift.report import build_report


def test_tolerance_matches_are_scored_as_r1_not_clean():
    ledger = pd.DataFrame(
        [{"order_id": "o1", "customer": "C", "order_date": "2026-07-01", "gross_amount": 1000.0, "status": "paid"}]
    )
    settlement = pd.DataFrame(
        [{"payment_id": "p1", "order_id": "o1", "settled_amount": 976.41, "fee": 20.0,
          "tax": 3.6, "settlement_date": "2026-07-02", "utr": "U1"}]
    )
    mr = MatchResult(tolerance_order_ids={"o1"})
    report = build_report(ledger, settlement, mr, gate_decisions=[])
    assert report.clean_tolerance == 1
    # rupees_reconciled should count the tolerance match's gross amount
    assert report.rupees_reconciled == 1000.0
