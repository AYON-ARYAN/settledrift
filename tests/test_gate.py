from settledrift.agent.investigate import Classification
from settledrift.gate import apply_gate


def test_r6_always_needs_review_even_at_max_confidence():
    c = Classification(order_id="o1", drift_class="R6", confidence=1.0, reasoning="no counterpart")
    decision = apply_gate(c)
    assert decision.status == "needs_review"


def test_high_confidence_non_r6_auto_resolves():
    c = Classification(order_id="o1", drift_class="R3", confidence=0.9, reasoning="partial refund")
    decision = apply_gate(c, threshold=0.75)
    assert decision.status == "auto_resolved"


def test_low_confidence_needs_review():
    c = Classification(order_id="o1", drift_class="R3", confidence=0.4, reasoning="not sure")
    decision = apply_gate(c, threshold=0.75)
    assert decision.status == "needs_review"


def test_fallback_classification_always_needs_review_regardless_of_confidence():
    c = Classification(
        order_id="o1", drift_class="R2", confidence=0.9, reasoning="fallback", fallback=True
    )
    decision = apply_gate(c, threshold=0.75)
    assert decision.status == "needs_review"


def test_threshold_boundary_is_inclusive():
    c = Classification(order_id="o1", drift_class="R2", confidence=0.75, reasoning="")
    decision = apply_gate(c, threshold=0.75)
    assert decision.status == "auto_resolved"
