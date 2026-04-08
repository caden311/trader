import signal
import time

import structlog

from config.settings import settings
from core.analyzer import PostAnalyzer
from core.executor import TradeExecutor
from core.monitor import TruthSocialMonitor
from core.risk import RiskManager
from store.database import Database

logger = structlog.get_logger()


class Orchestrator:
    def __init__(self):
        self.db = Database()
        self.monitor = TruthSocialMonitor(self.db)
        self.analyzer = PostAnalyzer()
        self.executor = TradeExecutor()
        self.risk = RiskManager(self.db)
        self.running = False

    def run(self) -> None:
        """Main loop: poll, analyze, trade."""
        self.running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info(
            "orchestrator_starting",
            paper_trading=settings.paper_trading,
            poll_interval=settings.poll_interval_seconds,
            confidence_threshold=settings.confidence_threshold,
            max_position_pct=settings.max_position_pct,
        )

        while self.running:
            try:
                self._tick()
            except Exception:
                logger.exception("tick_error")

            if self.running:
                time.sleep(settings.poll_interval_seconds)

        self._cleanup()

    def _tick(self) -> None:
        """Single iteration of the main loop."""

        # 1. Always poll for new posts (even after hours)
        new_posts = self.monitor.fetch_new_posts()

        # 2. Check market status once for the whole tick
        market_open = self.executor.is_market_open()

        # 3. If market just opened, drain analyses that arrived after hours
        if market_open:
            self._drain_pending_queue()

        if not new_posts:
            logger.debug("no_new_posts")
            return

        # 4. Analyze posts (batch if multiple arrived at once)
        if len(new_posts) > 1:
            analysis = self.analyzer.analyze_batch(new_posts)
            post_id = new_posts[0].id
        else:
            analysis = self.analyzer.analyze(new_posts[0])
            post_id = new_posts[0].id

        # Save analysis
        self.db.save_analysis(post_id, analysis)

        # 5. Queue for open if market is closed, otherwise trade now
        if not market_open and not settings.use_extended_hours:
            logger.info(
                "market_closed_trade_queued",
                post_id=post_id,
                direction=analysis.direction,
                confidence=analysis.confidence,
                tickers=analysis.affected_tickers,
            )
            self.db.queue_pending_analysis(post_id)
            return

        # 6. Risk check + execute
        self._evaluate_and_execute(post_id, analysis)

    def _drain_pending_queue(self) -> None:
        """Execute any analyses that were queued while the market was closed."""
        pending = self.db.get_pending_analyses()
        if not pending:
            return

        logger.info("draining_pending_queue", count=len(pending))
        equity = self.executor.get_account_equity()
        open_positions = self.executor.get_open_position_count()

        for post_id, analysis in pending:
            self.db.clear_pending_analysis(post_id)
            intents = self.risk.evaluate(
                analysis=analysis,
                post_id=post_id,
                portfolio_value=equity,
                current_positions=open_positions,
            )
            if not intents:
                logger.info("no_trades_after_risk_check", post_id=post_id)
                continue
            for intent in intents:
                record = self.executor.execute(intent)
                if record:
                    record.analysis_confidence = analysis.confidence
                    record.analysis_sentiment = analysis.sentiment
                    self.db.save_trade(record)
                    self.risk.record_trade_time()
                    logger.info(
                        "trade_executed",
                        symbol=record.symbol,
                        side=record.side,
                        qty=record.quantity,
                        order_id=record.order_id,
                    )
                    open_positions += 1

    def _evaluate_and_execute(self, post_id: str, analysis) -> None:
        """Run risk check and execute trades for a single analysis."""
        equity = self.executor.get_account_equity()
        open_positions = self.executor.get_open_position_count()

        intents = self.risk.evaluate(
            analysis=analysis,
            post_id=post_id,
            portfolio_value=equity,
            current_positions=open_positions,
        )

        if not intents:
            logger.info("no_trades_after_risk_check", post_id=post_id)
            return

        for intent in intents:
            record = self.executor.execute(intent)
            if record:
                record.analysis_confidence = analysis.confidence
                record.analysis_sentiment = analysis.sentiment
                self.db.save_trade(record)
                self.risk.record_trade_time()
                logger.info(
                    "trade_executed",
                    symbol=record.symbol,
                    side=record.side,
                    qty=record.quantity,
                    order_id=record.order_id,
                )

    def _shutdown(self, signum: int, frame) -> None:
        logger.info("shutdown_requested", signal=signum)
        self.running = False

    def _cleanup(self) -> None:
        self.db.close()
        logger.info("orchestrator_stopped")
