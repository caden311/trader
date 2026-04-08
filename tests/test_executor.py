from unittest.mock import MagicMock, patch

import pytest

from core.executor import TradeExecutor
from models.trade import TradeIntent, TradeSide


def _make_intent(side=TradeSide.BUY, **overrides) -> TradeIntent:
    defaults = {
        "symbol": "XLK",
        "side": side,
        "quantity": 1,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.05,
        "post_id": "post-1",
        "reasoning": "Test trade",
    }
    defaults.update(overrides)
    intent = TradeIntent(**defaults)
    intent._max_dollars = 500.0
    return intent


@pytest.fixture
def executor():
    with patch.object(TradeExecutor, "__init__", lambda self: None):
        ex = TradeExecutor()
        ex.client = MagicMock()
        return ex


def test_reject_equity_below_floor(executor):
    executor.get_account_details = MagicMock(return_value={
        "equity": 500.0,
        "buying_power": 10000.0,
        "cash": 10000.0,
        "maintenance_margin": 0,
    })

    intent = _make_intent()
    result = executor.execute(intent)
    assert result is None


def test_reject_insufficient_buying_power(executor):
    executor.get_account_details = MagicMock(return_value={
        "equity": 10000.0,
        "buying_power": 100.0,
        "cash": 100.0,
        "maintenance_margin": 0,
    })
    executor._get_latest_price = MagicMock(return_value=50.0)

    intent = _make_intent()
    result = executor.execute(intent)
    assert result is None


def test_reject_short_exposure_exceeded(executor):
    executor.get_account_details = MagicMock(return_value={
        "equity": 10000.0,
        "buying_power": 50000.0,
        "cash": 50000.0,
        "maintenance_margin": 0,
    })
    executor._get_latest_price = MagicMock(return_value=50.0)
    # Already have $1400 in shorts, max is 15% of $10000 = $1500
    executor.get_total_short_exposure = MagicMock(return_value=1400.0)

    intent = _make_intent(side=TradeSide.SELL)
    result = executor.execute(intent)
    assert result is None


def test_accept_order_with_sufficient_buying_power(executor):
    executor.get_account_details = MagicMock(return_value={
        "equity": 10000.0,
        "buying_power": 50000.0,
        "cash": 50000.0,
        "maintenance_margin": 0,
    })
    executor._get_latest_price = MagicMock(return_value=50.0)

    mock_order = MagicMock()
    mock_order.id = "order-123"
    mock_order.status = "accepted"
    executor.client.submit_order = MagicMock(return_value=mock_order)

    intent = _make_intent()
    result = executor.execute(intent)
    assert result is not None
    assert result.order_id == "order-123"


def test_buy_does_not_check_short_exposure(executor):
    executor.get_account_details = MagicMock(return_value={
        "equity": 10000.0,
        "buying_power": 50000.0,
        "cash": 50000.0,
        "maintenance_margin": 0,
    })
    executor._get_latest_price = MagicMock(return_value=50.0)

    mock_order = MagicMock()
    mock_order.id = "order-456"
    mock_order.status = "accepted"
    executor.client.submit_order = MagicMock(return_value=mock_order)

    intent = _make_intent(side=TradeSide.BUY)
    result = executor.execute(intent)
    assert result is not None
