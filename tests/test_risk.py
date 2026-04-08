from unittest.mock import MagicMock

import pytest

from core.risk import RiskManager
from models.analysis import AnalysisResult


@pytest.fixture
def db():
    mock_db = MagicMock()
    mock_db.get_trades_today.return_value = []
    return mock_db


@pytest.fixture
def risk(db):
    return RiskManager(db)


def _make_analysis(**overrides) -> AnalysisResult:
    defaults = {
        "is_relevant": True,
        "reasoning": "Test reasoning",
        "sentiment": 0.8,
        "affected_sectors": ["technology"],
        "affected_tickers": ["XLK"],
        "confidence": 0.85,
        "direction": "buy",
        "urgency": "immediate",
    }
    defaults.update(overrides)
    return AnalysisResult(**defaults)


def test_approve_good_analysis(risk):
    analysis = _make_analysis()
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert len(intents) == 1
    assert intents[0].symbol == "XLK"
    assert intents[0].side.value == "buy"


def test_reject_low_confidence(risk):
    analysis = _make_analysis(confidence=0.3)
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert intents == []


def test_reject_not_relevant(risk):
    analysis = _make_analysis(is_relevant=False)
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert intents == []


def test_reject_hold_direction(risk):
    analysis = _make_analysis(direction="hold")
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert intents == []


def test_reject_max_positions(risk):
    analysis = _make_analysis()
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=5)
    assert intents == []


def test_reject_cooldown(risk):
    analysis = _make_analysis()
    # First trade should go through
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert len(intents) == 1
    risk.record_trade_time()

    # Second trade should be blocked by cooldown
    intents = risk.evaluate(analysis, "post-2", portfolio_value=10000, current_positions=1)
    assert intents == []


def test_sell_direction(risk):
    analysis = _make_analysis(direction="sell", sentiment=-0.7)
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert len(intents) == 1
    assert intents[0].side.value == "sell"


def test_defaults_to_spy_when_no_tickers(risk):
    analysis = _make_analysis(affected_tickers=[], affected_sectors=[])
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert len(intents) == 1
    assert intents[0].symbol == "SPY"


def test_sell_uses_tighter_stop_loss(risk):
    analysis = _make_analysis(direction="sell", sentiment=-0.7)
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert len(intents) == 1
    assert intents[0].stop_loss_pct == 0.02
    assert intents[0].take_profit_pct == 0.04


def test_buy_uses_standard_stop_loss(risk):
    analysis = _make_analysis(direction="buy")
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert len(intents) == 1
    assert intents[0].stop_loss_pct == 0.03
    assert intents[0].take_profit_pct == 0.05


def test_sell_uses_smaller_position_size(risk):
    analysis = _make_analysis(direction="sell", sentiment=-0.7)
    intents = risk.evaluate(analysis, "post-1", portfolio_value=10000, current_positions=0)
    assert intents[0]._max_dollars == 10000 * 0.03  # max_single_short_pct

    analysis_buy = _make_analysis(direction="buy")
    intents_buy = risk.evaluate(analysis_buy, "post-2", portfolio_value=10000, current_positions=0)
    assert intents_buy[0]._max_dollars == 10000 * 0.05  # max_position_pct
