import csv

from settledrift.exceptions_export import write_exceptions_csv


def test_writes_one_row_per_exception(tmp_path):
    report = {
        "exceptions": [
            {"order_id": "o1", "predicted_class": "R6", "confidence": 0.9, "reason": "R6 is never auto-resolvable"},
            {"order_id": "o2", "predicted_class": "R5", "confidence": 0.4, "reason": "confidence 0.40 < threshold 0.75"},
        ]
    }
    out = tmp_path / "exceptions.csv"
    count = write_exceptions_csv(report, out)
    assert count == 2

    with open(out) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["order_id"] == "o1"
    assert rows[1]["predicted_class"] == "R5"


def test_writes_header_only_when_no_exceptions(tmp_path):
    out = tmp_path / "exceptions.csv"
    count = write_exceptions_csv({"exceptions": []}, out)
    assert count == 0
    with open(out) as f:
        rows = list(csv.DictReader(f))
    assert rows == []
