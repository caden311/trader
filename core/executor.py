from __future__ import annotations

from datetime import datetime

import structlog
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

from config.settings import settings
from models.trade import TradeIntent, TradeRecord, TradeSide

logger = structlog.get_logger()


class TradeExecutor:
    def __init__(self):
        self.client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=settings.paper_trading,
        )

    def get_account_details(self) -> dict:
        """Return key account fields for safety checks."""
        account = self.client.get_account()
        return {
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "cash": float(account.cash),
            "maintenance_margin": float(account.maintenance_margin or 0),
        }

    def get_account_equity(self) -> float:
        return self.get_account_details()["equity"]

    def get_open_position_count(self) -> int:
        positions = self.client.get_all_positions()
        return len(positions)

    def get_total_short_exposure(self) -> float:
        """Sum the market value of all current short positions."""
        positions = self.client.get_all_positions()
        return sum(
            abs(float(p.market_value))
            for p in positions
            if float(p.qty) < 0
        )

    def is_market_open(self) -> bool:
        clock = self.client.get_clock()
        return clock.is_open

    def execute(self, intent: TradeIntent) -> TradeRecord | None:
        """Execute a trade intent via Alpaca. Returns a TradeRecord or None on failure."""
        try:
            # Safety: check account health before any order
            account = self.get_account_details()

            if account["equity"] < settings.min_equity_floor:
                logger.warning(
                    "order_rejected_equity_floor",
                    symbol=intent.symbol,
                    equity=account["equity"],
                    floor=settings.min_equity_floor,
                )
                return None

            # Calculate quantity based on max dollars and current price
            max_dollars = getattr(intent, "_max_dollars", 500.0)
            price = self._get_latest_price(intent.symbol)
            if price <= 0:
                logger.error("invalid_price", symbol=intent.symbol, price=price)
                return None

            quantity = max(1, int(max_dollars / price))
            estimated_cost = price * quantity

            # Safety: buying power check with margin buffer
            required_buying_power = estimated_cost * settings.buying_power_multiplier
            if account["buying_power"] < required_buying_power:
                logger.warning(
                    "order_rejected_insufficient_buying_power",
                    symbol=intent.symbol,
                    side=intent.side.value,
                    estimated_cost=estimated_cost,
                    buying_power=account["buying_power"],
                    required=required_buying_power,
                )
                return None

            # Safety: short exposure cap
            if intent.side == TradeSide.SELL:
                current_short_exposure = self.get_total_short_exposure()
                max_short_exposure = account["equity"] * settings.max_short_exposure_pct
                if current_short_exposure + estimated_cost > max_short_exposure:
                    logger.warning(
                        "order_rejected_short_exposure_limit",
                        symbol=intent.symbol,
                        current_short_exposure=current_short_exposure,
                        additional=estimated_cost,
                        max_allowed=max_short_exposure,
                    )
                    return None

            side = (
                OrderSide.BUY if intent.side == TradeSide.BUY else OrderSide.SELL
            )

            # Calculate stop-loss and take-profit prices
            if side == OrderSide.BUY:
                stop_price = round(price * (1 - intent.stop_loss_pct), 2)
                profit_price = round(price * (1 + intent.take_profit_pct), 2)
            else:
                stop_price = round(price * (1 + intent.stop_loss_pct), 2)
                profit_price = round(price * (1 - intent.take_profit_pct), 2)

            order_request = MarketOrderRequest(
                symbol=intent.symbol,
                qty=quantity,
                side=side,
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.BRACKET,
                stop_loss=StopLossRequest(stop_price=stop_price),
                take_profit=TakeProfitRequest(limit_price=profit_price),
            )

            logger.info(
                "submitting_order",
                symbol=intent.symbol,
                side=side.value,
                qty=quantity,
                estimated_cost=price * quantity,
            )

            order = self.client.submit_order(order_request)

            record = TradeRecord(
                post_id=intent.post_id,
                symbol=intent.symbol,
                side=intent.side.value,
                quantity=quantity,
                order_id=str(order.id),
                status=str(order.status),
                executed_at=datetime.now(),
                entry_price=price,
                analysis_confidence=0.0,  # Will be set by orchestrator
                analysis_sentiment=0.0,
            )

            logger.info(
                "order_submitted",
                order_id=order.id,
                symbol=intent.symbol,
                status=order.status,
            )

            return record

        except Exception as e:
            logger.error(
                "order_failed",
                symbol=intent.symbol,
                error=str(e),
            )
            return None

    def _get_latest_price(self, symbol: str) -> float:
        """Get the latest trade price for a symbol."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest

            data_client = StockHistoricalDataClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
            )
            request = StockLatestTradeRequest(symbol_or_symbols=symbol)
            trades = data_client.get_stock_latest_trade(request)
            return float(trades[symbol].price)
        except Exception as e:
            logger.warning("price_fetch_failed", symbol=symbol, error=str(e))
            return 0.0
