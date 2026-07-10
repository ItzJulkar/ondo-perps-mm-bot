import logging
import signal
import time

from src.config import AppConfig
from src.daemon import clear_pid, stop_requested
from src.exchange.ondo import OndoClient
from src.mm.engine import MarketMakerEngine

logger = logging.getLogger(__name__)


class MmBot:
    def __init__(self, config: AppConfig, exchange: OndoClient):
        self.config = config
        self.exchange = exchange
        self.engine = MarketMakerEngine(config, exchange)
        self._running = False

    def _setup_leverage(self) -> None:
        for market in self.config.markets:
            try:
                self.exchange.set_leverage(market, self.config.max_leverage_for(market))
                logger.info("Set leverage %dx on %s", self.config.max_leverage_for(market), market)
            except Exception:
                logger.exception("Failed to set leverage on %s", market)

    def run(self) -> None:
        self._running = True
        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)

        mode = "DRY-RUN" if self.config.bot.dry_run else "LIVE"
        logger.info(
            "Professional MM bot [%s] | markets=%s | budget=%.0f%% margin | prefix=%s",
            mode,
            ",".join(self.config.markets),
            self.config.mm.margin_budget_pct,
            self.config.bot.order_prefix,
        )

        if not self.config.bot.dry_run:
            self._setup_leverage()

        while self._running:
            if stop_requested():
                logger.info("Stop requested — cancelling MM quotes and shutting down")
                for market in self.config.markets:
                    self.exchange.cancel_bot_orders(market)
                self._running = False
                break
            try:
                self.engine.tick()
            except Exception:
                logger.exception("MM tick failed")
            time.sleep(self.config.bot.poll_interval_sec)

        clear_pid()
        logger.info("MM bot stopped")

    def _handle_stop(self, signum, frame) -> None:
        logger.info("Shutdown signal (%s)", signum)
        self._running = False