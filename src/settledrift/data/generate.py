"""Synthetic ledger + settlement generator.

Produces a merchant's internal sales ledger and a Razorpay-style settlement
report from the same underlying set of "true" transactions, then deliberately
injects each class of the R1-R6 taxonomy at a known rate. The ground truth is
written to a separate file that the matcher and agent never see — only the
scorer reads it, exactly the way DriftBench's oracle spec never enters the
agent's workspace.
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

FEE_RATE = 0.02  # Razorpay's standard blended fee, illustrative
GST_RATE = 0.18  # GST on the fee itself

CUSTOMERS = [
    "Aarav Mehta", "Diya Sharma", "Kabir Nair", "Isha Reddy", "Vihaan Rao",
    "Ananya Iyer", "Aditya Kapoor", "Saanvi Joshi", "Arjun Menon", "Myra Gupta",
    "Reyansh Pillai", "Kiara Bose", "Vivaan Shetty", "Anika Verma", "Ayaan Desai",
]


@dataclass
class Transaction:
    order_id: str
    payment_id: str
    customer: str
    order_date: date
    gross_amount: float


def _rid(prefix: str, rng: random.Random) -> str:
    return f"{prefix}_{''.join(rng.choices('0123456789ABCDEFGHJKLMNPQRSTUVWXYZ', k=14))}"


def _fee_net(gross: float) -> tuple[float, float, float]:
    """Return (fee, tax, net) for a gross amount, Razorpay-style."""
    fee = round(gross * FEE_RATE, 2)
    tax = round(fee * GST_RATE, 2)
    net = round(gross - fee - tax, 2)
    return fee, tax, net


def generate(
    out_dir: Path,
    n: int = 120,
    seed: int = 42,
    rates: dict[str, float] | None = None,
) -> None:
    """Generate ledger.csv, settlement.csv, and ground_truth.jsonl under out_dir.

    `rates` maps R1..R6 to the fraction of the n base transactions that get
    that mutation applied. Whatever fraction remains is CLEAN — an exact
    deterministic match. Defaults are chosen to be a realistic, not-too-easy
    mix: nothing so it always adds up before validation runs.
    """
    rates = rates or {
        "R1": 0.12,
        "R2": 0.15,
        "R3": 0.08,
        "R4": 0.05,
        "R5": 0.04,
        "R6": 0.06,
    }
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    start = date(2026, 7, 1)
    base: list[Transaction] = []
    for _ in range(n):
        order_date = start + timedelta(days=rng.randint(0, 45))
        gross = round(rng.uniform(199, 24999), 2)
        base.append(
            Transaction(
                order_id=_rid("order", rng),
                payment_id=_rid("pay", rng),
                customer=rng.choice(CUSTOMERS),
                order_date=order_date,
                gross_amount=gross,
            )
        )

    # Assign each transaction exactly one class, respecting the requested
    # rates (rounded to whole transactions), remainder is CLEAN.
    remaining = list(base)
    rng.shuffle(remaining)
    assignment: dict[str, str] = {}
    idx = 0
    for cls, rate in rates.items():
        count = round(n * rate)
        for txn in remaining[idx : idx + count]:
            assignment[txn.order_id] = cls
        idx += count
    for txn in base:
        assignment.setdefault(txn.order_id, "CLEAN")

    ledger_rows = []
    settlement_rows = []
    ground_truth = []

    for txn in base:
        cls = assignment[txn.order_id]
        fee, tax, net = _fee_net(txn.gross_amount)

        if cls == "CLEAN":
            ledger_rows.append(_ledger_row(txn, txn.gross_amount, "paid"))
            settlement_rows.append(
                _settlement_row(txn, net, fee, tax, txn.order_date + timedelta(days=2))
            )
            ground_truth.append(_gt(txn.order_id, "CLEAN", [txn.payment_id]))

        elif cls == "R1":
            # Ledger's expected-net uses a slightly different rounding
            # convention than the settlement's actual fee math.
            drift = rng.choice([0.01, 0.02, 0.03, -0.01, -0.02])
            ledger_rows.append(_ledger_row(txn, txn.gross_amount, "paid"))
            settlement_rows.append(
                _settlement_row(
                    txn, round(net + drift, 2), fee, tax, txn.order_date + timedelta(days=2)
                )
            )
            ground_truth.append(_gt(txn.order_id, "R1", [txn.payment_id]))

        elif cls == "R2":
            lag = rng.randint(3, 9)  # beyond a naive same-day/next-day window
            ledger_rows.append(_ledger_row(txn, txn.gross_amount, "paid"))
            settlement_rows.append(
                _settlement_row(txn, net, fee, tax, txn.order_date + timedelta(days=lag))
            )
            ground_truth.append(_gt(txn.order_id, "R2", [txn.payment_id]))

        elif cls == "R3":
            refund = round(txn.gross_amount * rng.uniform(0.2, 0.6), 2)
            refunded_gross = round(txn.gross_amount - refund, 2)
            r_fee, r_tax, r_net = _fee_net(refunded_gross)
            ledger_rows.append(_ledger_row(txn, txn.gross_amount, "partially_refunded"))
            settlement_rows.append(
                _settlement_row(txn, r_net, r_fee, r_tax, txn.order_date + timedelta(days=2))
            )
            ground_truth.append(_gt(txn.order_id, "R3", [txn.payment_id]))

        elif cls == "R4":
            split = round(net * rng.uniform(0.3, 0.7), 2)
            remainder = round(net - split, 2)
            ledger_rows.append(_ledger_row(txn, txn.gross_amount, "paid"))
            pid_b = _rid("pay", rng)
            settlement_rows.append(
                _settlement_row(txn, split, fee, tax, txn.order_date + timedelta(days=2))
            )
            settlement_rows.append(
                _settlement_row(
                    txn, remainder, 0.0, 0.0, txn.order_date + timedelta(days=5), payment_id=pid_b
                )
            )
            ground_truth.append(_gt(txn.order_id, "R4", [txn.payment_id, pid_b]))

        elif cls == "R5":
            ledger_rows.append(_ledger_row(txn, txn.gross_amount, "paid"))
            ledger_rows.append(_ledger_row(txn, txn.gross_amount, "paid"))  # accidental dup
            settlement_rows.append(
                _settlement_row(txn, net, fee, tax, txn.order_date + timedelta(days=2))
            )
            ground_truth.append(_gt(txn.order_id, "R5", [txn.payment_id]))

        elif cls == "R6":
            # Coin flip: either the ledger has it but settlement hasn't
            # happened yet, or settlement has a row the ledger never recorded.
            if rng.random() < 0.5:
                ledger_rows.append(_ledger_row(txn, txn.gross_amount, "paid"))
                # no settlement row at all
            else:
                settlement_rows.append(
                    _settlement_row(txn, net, fee, tax, txn.order_date + timedelta(days=2))
                )
                # no ledger row at all
            ground_truth.append(_gt(txn.order_id, "R6", [txn.payment_id]))

    _write_csv(out_dir / "ledger.csv", ledger_rows,
               ["order_id", "customer", "order_date", "gross_amount", "status"])
    _write_csv(out_dir / "settlement.csv", settlement_rows,
               ["payment_id", "order_id", "settled_amount", "fee", "tax", "settlement_date", "utr"])
    with open(out_dir / "ground_truth.jsonl", "w") as f:
        for row in ground_truth:
            f.write(json.dumps(row) + "\n")


def _ledger_row(txn: Transaction, gross: float, status: str) -> dict:
    return {
        "order_id": txn.order_id,
        "customer": txn.customer,
        "order_date": txn.order_date.isoformat(),
        "gross_amount": gross,
        "status": status,
    }


def _settlement_row(
    txn: Transaction, net: float, fee: float, tax: float, settle_date: date,
    payment_id: str | None = None,
) -> dict:
    return {
        "payment_id": payment_id or txn.payment_id,
        "order_id": txn.order_id,
        "settled_amount": net,
        "fee": fee,
        "tax": tax,
        "settlement_date": settle_date.isoformat(),
        "utr": f"UTR{txn.order_id[-8:]}",
    }


def _gt(order_id: str, cls: str, payment_ids: list[str]) -> dict:
    return {"order_id": order_id, "class": cls, "payment_ids": payment_ids}


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
