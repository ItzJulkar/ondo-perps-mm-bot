import logging
import time
from decimal import Decimal

from src.config import AppConfig
from src.exchange.ondo import OndoClient
from src.mm.quoter import build_quote_plan
from src.mm.risk import RiskManager
from src.models import Order, QuotePlan, Side

logger = logging.getLogger(__name__)


class MarketMakerEngine:
    """
    Pro MM loop:
    - Quote at the touch (1 tick from BBO) so orders actually fill
    - Keep quotes resting in queue; only cancel/replace when BBO moves
    - Inventory + portfolio skew shifts reservation a few bps
    """

    def __init__(self, config: AppConfig, exchange: OndoClient):
        self.config = config
        self.exchange = exchange
        self.risk = RiskManager(config)
        self._last_quote_at: dict[str, float] = {}
        self._last_bbo: dict[str, tuple[Decimal, Decimal]] = {}
        self._last_skew: dict[str, int] = {}
        self._max_inventory_usd = config.portfolio.max_portfolio_delta_usd

    def _skew_bucket(self, plan: QuotePlan) -> int:
        skew = plan.inventory_util * self.config.mm.inventory_skew_bps
        if self.config.portfolio.hedge_enabled:
            skew += plan.portfolio_delta_usd / max(self.config.portfolio.max_portfolio_delta_usd, 1)
        return int(skew * 10)

    def _needs_requote(self, market: str, snap, open_orders: list[Order], plan: QuotePlan) -> bool:
        if not open_orders:
            return True

        if len(open_orders) < self.config.mm.levels_per_side * 2:
            return True

        bbo = (snap.best_bid, snap.best_ask)
        prev_bbo = self._last_bbo.get(market)
        skew_bucket = self._skew_bucket(plan)
        prev_skew = self._last_skew.get(market)

        bbo_moved = prev_bbo is None or bbo != prev_bbo
        skew_moved = prev_skew is None or skew_bucket != prev_skew

        if not bbo_moved and not skew_moved:
            return False

        now = time.time()
        last = self._last_quote_at.get(market, 0)
        if now - last < self.config.mm.quote_refresh_sec:
            return False

        target_prices = {(lvl.side, lvl.level, lvl.price) for lvl in plan.bid_levels + plan.ask_levels}
        have_prices = set()
        for o in open_orders:
            level = 0
            if o.client_order_id:
                parts = o.client_order_id.split("_")
                if len(parts) >= 2 and parts[-2].isdigit():
                    level = int(parts[-2])
            have_prices.add((o.side, level, o.price))

        if bbo_moved and have_prices != {(s, l, p) for s, l, p in target_prices}:
            return True
        if skew_moved:
            return True
        return False

    def _cancel_and_quote(self, plan: QuotePlan, snap) -> None:
        cancelled = self.exchange.cancel_bot_orders(plan.market)
        levels = plan.bid_levels + plan.ask_levels
        placed = self.exchange.place_batch_quotes(plan.market, levels, plan.size)

        self._last_quote_at[plan.market] = time.time()
        self._last_bbo[plan.market] = (snap.best_bid, snap.best_ask)
        self._last_skew[plan.market] = self._skew_bucket(plan)

        bid = plan.bid_levels[0].price if plan.bid_levels else "?"
        ask = plan.ask_levels[0].price if plan.ask_levels else "?"
        logger.info(
            "[%s] MM quote @ touch | bid=%s ask=%s | BBO %s/%s | size=%s | inv=%.0f%% | placed=%d",
            plan.market,
            bid,
            ask,
            snap.best_bid,
            snap.best_ask,
            plan.size,
            plan.inventory_util * 100,
            len(placed),
        )

    def tick(self) -> None:
        balance = self.exchange.get_balance()
        positions = self.exchange.get_positions()

        vols = [self.exchange.get_realized_vol_pct(m) for m in self.config.markets]
        max_vol = max(vols) if vols else 0.0

        risk = self.risk.check(balance, max_vol)
        if not risk.ok:
            logger.warning("MM paused: %s", risk.reason)
            for market in self.config.markets:
                self.exchange.cancel_bot_orders(market)
            return

        budget = Decimal(str(self.risk.mm_budget_margin(balance)))

        for i, market in enumerate(self.config.markets):
            snap = self.exchange.get_market_snapshot(market)
            pos = next((p for p in positions if p.market == market), None)
            vol = vols[i] if i < len(vols) else 0.15

            plan = build_quote_plan(
                self.config,
                self.exchange,
                market,
                snap,
                pos,
                positions,
                vol,
                budget,
                self._max_inventory_usd,
            )

            open_orders = self.exchange.get_bot_orders(market)
            if self._needs_requote(market, snap, open_orders, plan):
                self._cancel_and_quote(plan, snap)