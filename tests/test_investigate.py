from dataclasses import dataclass, field

import pandas as pd

from settledrift.agent.investigate import investigate_order
from settledrift.agent.providers import ModelResponse
from settledrift.agent.tools import Toolset


@dataclass
class ScriptedProvider:
    """Fake provider that returns a fixed sequence of responses, one per call.
    Lets tests exercise the tool-call round-trip and the JSON-parsing paths
    without needing a live Ollama model."""

    responses: list[str]
    calls: list = field(default_factory=list)

    def complete(self, system: str, user: str) -> ModelResponse:
        self.calls.append((system, user))
        return ModelResponse(text=self.responses[len(self.calls) - 1])


def _toolset():
    ledger = pd.DataFrame(
        [
            {"order_id": "o1", "customer": "Aarav Mehta", "order_date": "2026-07-01",
             "gross_amount": 1000.0, "status": "paid"},
        ]
    )
    settlement = pd.DataFrame(
        [
            {"payment_id": "p1", "order_id": "o1", "settled_amount": 976.4, "fee": 20.0,
             "tax": 3.6, "settlement_date": "2026-07-10", "utr": "UTR1"},
        ]
    )
    return Toolset(ledger=ledger, settlement=settlement)


def test_direct_final_answer_parses_correctly():
    provider = ScriptedProvider(responses=['{"class": "R2", "confidence": 0.85, "reasoning": "9 day lag"}'])
    result = investigate_order("o1", _toolset(), provider)
    assert result.drift_class == "R2"
    assert result.confidence == 0.85
    assert not result.fallback
    assert len(provider.calls) == 1


def test_tool_call_round_trip_then_final_answer():
    provider = ScriptedProvider(
        responses=[
            '{"tool": "get_customer_orders", "customer": "Aarav Mehta"}',
            '{"class": "R5", "confidence": 0.7, "reasoning": "duplicate booking"}',
        ]
    )
    result = investigate_order("o1", _toolset(), provider, max_tool_calls=1)
    assert result.drift_class == "R5"
    assert result.tool_calls == 1
    assert len(provider.calls) == 2
    assert "get_customer_orders" in provider.calls[1][1]


def test_unparseable_output_falls_back_to_rule_based():
    provider = ScriptedProvider(responses=["I am not sure, sorry, no JSON here."])
    result = investigate_order("o1", _toolset(), provider)
    assert result.fallback is True
    assert result.confidence < 0.75  # never lets a garbage response auto-resolve


def test_unknown_class_falls_back_to_rule_based():
    provider = ScriptedProvider(responses=['{"class": "R9", "confidence": 0.9, "reasoning": "made up"}'])
    result = investigate_order("o1", _toolset(), provider)
    assert result.fallback is True


def test_confidence_is_clamped_to_unit_interval():
    provider = ScriptedProvider(responses=['{"class": "R2", "confidence": 5.0, "reasoning": "overclaiming"}'])
    result = investigate_order("o1", _toolset(), provider)
    assert result.confidence == 1.0
