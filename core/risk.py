from __future__ import annotations

from datetime import datetime

import structlog

from config.sector_map import sectors_to_tickers
from config.settings import settings
from models.analysis import AnalysisResult
from models.trade import TradeIntent, TradeSide
from store.database import Database

logger = structlog.get_logger()


class RiskManager:
    def __init__(self, db: Database):
        self.db = db
        self.last_trade_time: datetime | None = None

    def evaluate(
        self,
        analysis: AnalysisResult,
        post_id: str,
        portfolio_value: float,
        current_positions: int,
    ) -> list[TradeIntent]:
        """Evaluate an analysis against risk rules and return trade intents if approved."""

        # Check confidence threshold
        if analysis.confidence < settings.confidence_threshold:
            logger.info(
                "risk_rejected_low_confidence",
                confidence=analysis.confidence,
                threshold=settings.confidence_threshold,
            )
            return []

        # Check if relevant
        if not analysis.is_relevant:
            logger.info("risk_rejected_not_relevant")
            return []

        # Check direction
        if analysis.direction == "hold":
            logger.info("risk_rejected_hold_direction")
            return []

        # Check cooldown
        if self.last_trade_time:
            elapsed = (datetime.now() - self.last_trade_time).total_seconds()
            if elapsed < settings.trade_cooldown_seconds:
                remaining = settings.trade_cooldown_seconds - elapsed
                logger.info("risk_rejected_cooldown", remaining_seconds=remaining)
                return []

        # Check max open positions
        if current_positions >= settings.max_open_positions:
            logger.info(
                "risk_rejected_max_positions",
                current=current_positions,
                max=settings.max_open_positions,
            )
            return []

        # Check daily loss limit
        trades_today = self.db.get_trades_today()
        if self._daily_loss_exceeded(trades_today, portfolio_value):
            logger.info("risk_rejected_daily_loss_limit")
            return []

        # Determine tickers to trade
        tickers = analysis.affected_tickers or sectors_to_tickers(
            analysis.affected_sectors
        )

        # Calculate side-dependent risk parameters
        side = TradeSide.BUY if analysis.direction == "buy" else TradeSide.SELL

        if side == TradeSide.SELL:
            stop_loss = settings.short_stop_loss_pct
            take_profit = settings.short_take_profit_pct
            max_dollars_per_trade = portfolio_value * settings.max_single_short_pct
        else:
            stop_loss = settings.long_stop_loss_pct
            take_profit = settings.long_take_profit_pct
            max_dollars_per_trade = portfolio_value * settings.max_position_pct

        intents = []
        for ticker in tickers:
            if current_positions + len(intents) >= settings.max_open_positions:
                break

            intent = TradeIntent(
                symbol=ticker,
                side=side,
                quantity=1,  # Will be calculated by executor based on price
                stop_loss_pct=stop_loss,
                take_profit_pct=take_profit,
                post_id=post_id,
                reasoning=analysis.reasoning,
            )
            # Store max dollars for the executor to use for qty calculation
            intent._max_dollars = max_dollars_per_trade
            intents.append(intent)

        logger.info(
            "risk_approved",
            trade_count=len(intents),
            tickers=[i.symbol for i in intents],
            side=side.value,
        )

        return intents

    def record_trade_time(self) -> None:
        self.last_trade_time = datetime.now()

    def _daily_loss_exceeded(
        self, trades_today: list[dict], portfolio_value: float
    ) -> bool:
        """Check if we've exceeded the daily loss limit. Conservative: count all trades as potential losses."""
        if not trades_today:
            return False
        total_exposure = sum(
            (t.get("entry_price", 0) or 0) * t.get("quantity", 0)
            for t in trades_today
        )
        max_daily_loss = portfolio_value * settings.daily_loss_limit_pct
        # Rough check: if total exposure * stop_loss_pct exceeds daily limit
        potential_loss = total_exposure * max(
            settings.long_stop_loss_pct, settings.short_stop_loss_pct
        )
        return potential_loss > max_daily_loss
