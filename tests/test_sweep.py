import json

from settledrift.sweep import sweep_thresholds


def _write_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_higher_threshold_never_auto_resolves_more_than_lower_threshold(tmp_path):
    journal = tmp_path / "journal.jsonl"
    _write_jsonl(journal, [
        {"event": "investigated", "order_id": "o1", "predicted_class": "R4", "confidence": 0.6, "fallback": False},
        {"event": "investigated", "order_id": "o2", "predicted_class": "R5", "confidence": 0.8, "fallback": False},
        {"event": "investigated", "order_id": "o3", "predicted_class": "R4", "confidence": 0.95, "fallback": False},
    ])
    points = sweep_thresholds(journal, ground_truth_path=None, thresholds=[0.5, 0.75, 0.9, 1.0])
    autos = [p.auto_resolved for p in points]
    assert autos == sorted(autos, reverse=True)  # monotonically non-increasing as threshold rises
    assert points[0].auto_resolved == 3  # threshold 0.5: all three clear the bar (0.6, 0.8, 0.95)
    assert points[-1].auto_resolved == 0  # threshold 1.0: none of 0.6/0.8/0.95 clear it


def test_r6_never_auto_resolves_at_any_threshold(tmp_path):
    journal = tmp_path / "journal.jsonl"
    _write_jsonl(journal, [
        {"event": "investigated", "order_id": "o1", "predicted_class": "R6", "confidence": 1.0, "fallback": False},
    ])
    points = sweep_thresholds(journal, ground_truth_path=None, thresholds=[0.0, 0.5, 1.0])
    assert all(p.auto_resolved == 0 for p in points)
    assert all(p.needs_review == 1 for p in points)


def test_fallback_classification_never_auto_resolves(tmp_path):
    journal = tmp_path / "journal.jsonl"
    _write_jsonl(journal, [
        {"event": "investigated", "order_id": "o1", "predicted_class": "R2", "confidence": 0.99, "fallback": True},
    ])
    points = sweep_thresholds(journal, ground_truth_path=None, thresholds=[0.0])
    assert points[0].auto_resolved == 0


def test_wrong_but_auto_resolved_is_detected_against_ground_truth(tmp_path):
    journal = tmp_path / "journal.jsonl"
    gt = tmp_path / "ground_truth.jsonl"
    _write_jsonl(journal, [
        {"event": "investigated", "order_id": "o1", "predicted_class": "R4", "confidence": 0.8, "fallback": False},
    ])
    _write_jsonl(gt, [{"order_id": "o1", "class": "R5", "payment_ids": []}])
    points = sweep_thresholds(journal, gt, thresholds=[0.75])
    assert points[0].auto_resolved == 1
    assert points[0].wrong_among_auto_resolved == 1
    assert points[0].error_leak_rate == 1.0
