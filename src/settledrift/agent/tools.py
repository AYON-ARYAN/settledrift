"""Read-only evidence lookups the agent may call. None of these can write
back to ledger.csv or settlement.csv — they only ever return copies of rows
already loaded in memory, mirroring DriftBench's rule that the investigation
layer can look but never touch."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from settledrift.matcher import expected_net


@dataclass
class Toolset:
    ledger: pd.DataFrame
    settlement: pd.DataFrame

    def get_ledger_rows(self, order_id: str) -> list[dict]:
        rows = self.ledger.loc[self.ledger["order_id"] == order_id]
        return rows.to_dict(orient="records")

    def get_settlement_rows(self, order_id: str) -> list[dict]:
        rows = self.settlement.loc[self.settlement["order_id"] == order_id]
        return rows.to_dict(orient="records")

    def get_customer_orders(self, customer: str) -> list[str]:
        rows = self.ledger.loc[self.ledger["customer"] == customer]
        return sorted(rows["order_id"].unique().tolist())

    def evidence_bundle(self, order_id: str) -> dict:
        """Every number the model would otherwise have to compute itself —
        diff_rupees, lag_days, row counts — is precomputed here. A 3B local
        model is unreliable at rupee/date arithmetic; giving it the answer
        to "how big is the gap" as a fact rather than a mental-math exercise
        is what actually made R1-vs-R2 and R6 detection usable in practice.
        """
        ledger_rows = self.get_ledger_rows(order_id)
        settlement_rows = self.get_settlement_rows(order_id)

        expected = None
        diff_rupees = None
        lag_days = None
        if len(ledger_rows) == 1 and len(settlement_rows) == 1:
            expected = expected_net(float(ledger_rows[0]["gross_amount"]))
            actual = float(settlement_rows[0]["settled_amount"])
            diff_rupees = round(abs(expected - actual), 2)
            lag_days = (
                pd.Timestamp(settlement_rows[0]["settlement_date"])
                - pd.Timestamp(ledger_rows[0]["order_date"])
            ).days

        return {
            "order_id": order_id,
            "ledger_row_count": len(ledger_rows),
            "settlement_row_count": len(settlement_rows),
            "ledger_rows": ledger_rows,
            "settlement_rows": settlement_rows,
            "expected_net_if_single_row_each_side": expected,
            "diff_rupees_expected_vs_actual": diff_rupees,
            "settlement_lag_days": lag_days,
        }
