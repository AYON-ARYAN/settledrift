from settledrift.dashboard import render_dashboard


def _sample_report():
    return {
        "total_orders": 10,
        "clean_exact": 5,
        "clean_tolerance": 1,
        "unresolved_by_matcher": 4,
        "agent_auto_resolved": 3,
        "agent_needs_review": 1,
        "match_rate": 0.9,
        "rupees_reconciled": 123456.78,
        "overall_classification_accuracy": 1.0,
        "per_class": {
            "CLEAN": {"true_count": 5, "predicted_count": 5, "correct": 5, "precision": 1.0, "recall": 1.0},
            "R6": {"true_count": 1, "predicted_count": 1, "correct": 1, "precision": 1.0, "recall": 1.0},
        },
        "exception_count": 1,
        "exceptions": [
            {"order_id": "order_ABC123", "predicted_class": "R6", "confidence": 0.95, "reason": "R6 is never auto-resolvable"}
        ],
    }


def test_render_dashboard_is_self_contained_html():
    html_out = render_dashboard(_sample_report(), journal=[], title="Test Run")
    assert html_out.startswith("<!doctype html>")
    assert "<title>Test Run</title>" in html_out
    assert "order_ABC123" in html_out
    assert "₹123,456.78" in html_out
    assert "<script" not in html_out  # no external JS, nothing to break offline
    assert "http://" not in html_out and "https://" not in html_out  # no network calls


def test_render_dashboard_handles_zero_exceptions():
    report = _sample_report()
    report["exceptions"] = []
    html_out = render_dashboard(report, journal=[])
    assert "No exceptions in this run." in html_out


def test_render_dashboard_escapes_untrusted_fields():
    report = _sample_report()
    report["exceptions"] = [
        {"order_id": "<script>alert(1)</script>", "predicted_class": "R6", "confidence": 0.9, "reason": "x"}
    ]
    html_out = render_dashboard(report, journal=[])
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out
