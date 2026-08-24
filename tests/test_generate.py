import json
from collections import Counter

from settledrift.data.generate import generate


def test_generate_ground_truth_matches_requested_rates(tmp_path):
    generate(tmp_path, n=120, seed=42)
    with open(tmp_path / "ground_truth.jsonl") as f:
        classes = [json.loads(line)["class"] for line in f]
    counts = Counter(classes)
    assert sum(counts.values()) == 120
    # default rates: R1=.12 R2=.15 R3=.08 R4=.05 R5=.04 R6=.06 -> rest CLEAN
    assert counts["R1"] == 14
    assert counts["R2"] == 18
    assert counts["R3"] == 10
    assert counts["R4"] == 6
    assert counts["R5"] == 5
    assert counts["R6"] == 7
    assert counts["CLEAN"] == 60


def test_generate_is_deterministic_for_a_fixed_seed(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    generate(out_a, n=60, seed=7)
    generate(out_b, n=60, seed=7)
    assert (out_a / "ledger.csv").read_text() == (out_b / "ledger.csv").read_text()
    assert (out_a / "settlement.csv").read_text() == (out_b / "settlement.csv").read_text()


def test_r4_split_produces_two_settlement_rows_for_one_order(tmp_path):
    generate(tmp_path, n=120, seed=42)
    with open(tmp_path / "ground_truth.jsonl") as f:
        r4_orders = [json.loads(line)["order_id"] for line in f if json.loads(line)["class"] == "R4"]
    import pandas as pd

    settlement = pd.read_csv(tmp_path / "settlement.csv")
    for oid in r4_orders:
        assert len(settlement.loc[settlement["order_id"] == oid]) == 2


def test_r5_duplicate_produces_two_ledger_rows_for_one_order(tmp_path):
    generate(tmp_path, n=120, seed=42)
    with open(tmp_path / "ground_truth.jsonl") as f:
        r5_orders = [json.loads(line)["order_id"] for line in f if json.loads(line)["class"] == "R5"]
    import pandas as pd

    ledger = pd.read_csv(tmp_path / "ledger.csv")
    for oid in r5_orders:
        assert len(ledger.loc[ledger["order_id"] == oid]) == 2


def test_r6_missing_counterpart_appears_on_exactly_one_side(tmp_path):
    generate(tmp_path, n=120, seed=42)
    with open(tmp_path / "ground_truth.jsonl") as f:
        r6_orders = [json.loads(line)["order_id"] for line in f if json.loads(line)["class"] == "R6"]
    import pandas as pd

    ledger = pd.read_csv(tmp_path / "ledger.csv")
    settlement = pd.read_csv(tmp_path / "settlement.csv")
    for oid in r6_orders:
        in_ledger = len(ledger.loc[ledger["order_id"] == oid])
        in_settlement = len(settlement.loc[settlement["order_id"] == oid])
        assert (in_ledger, in_settlement) in {(1, 0), (0, 1)}
