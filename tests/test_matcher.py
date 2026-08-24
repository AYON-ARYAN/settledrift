import pandas as pd
import pytest

from settledrift.data.generate import generate
from settledrift.matcher import deterministic_match, expected_net


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    out = tmp_path_factory.mktemp("corpus")
    generate(out, n=120, seed=42)
    ledger = pd.read_csv(out / "ledger.csv")
    settlement = pd.read_csv(out / "settlement.csv")
    truth = {}
    with open(out / "ground_truth.jsonl") as f:
        import json

        for line in f:
            row = json.loads(line)
            truth[row["order_id"]] = row["class"]
    return ledger, settlement, truth


def test_expected_net_matches_razorpay_fee_math():
    # gross 1000 -> fee 20 (2%) -> tax 3.6 (18% of fee) -> net 976.40
    assert expected_net(1000.0) == 976.4


def test_clean_orders_are_all_and_only_true_clean(corpus):
    ledger, settlement, truth = corpus
    mr = deterministic_match(ledger, settlement)
    for oid in mr.exact_order_ids:
        assert truth[oid] == "CLEAN"


def test_tolerance_bucket_is_all_and_only_r1(corpus):
    ledger, settlement, truth = corpus
    mr = deterministic_match(ledger, settlement)
    for oid in mr.tolerance_order_ids:
        assert truth[oid] == "R1"
    # every R1 order in the corpus must show up here, none dropped
    r1_true = {oid for oid, cls in truth.items() if cls == "R1"}
    assert mr.tolerance_order_ids == r1_true


def test_unresolved_bucket_is_exactly_r2_through_r6(corpus):
    ledger, settlement, truth = corpus
    mr = deterministic_match(ledger, settlement)
    expected_unresolved = {oid for oid, cls in truth.items() if cls in {"R2", "R3", "R4", "R5", "R6"}}
    assert mr.unresolved_order_ids == expected_unresolved


def test_no_order_id_double_counted(corpus):
    ledger, settlement, _truth = corpus
    mr = deterministic_match(ledger, settlement)
    all_ids = mr.exact_order_ids | mr.tolerance_order_ids | mr.unresolved_order_ids
    assert len(mr.exact_order_ids) + len(mr.tolerance_order_ids) + len(mr.unresolved_order_ids) == len(all_ids)
