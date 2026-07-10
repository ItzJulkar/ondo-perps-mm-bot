from decimal import Decimal

from src.config import AppConfig
from src.exchange.ondo import OndoClient
from src.mm.inventory import inventory_skew_bps, inventory_utilization
from src.mm.portfolio import portfolio_delta_usd, portfolio_skew_bps
from src.models import MarketInfo, MarketSnapshot, Position, QuoteLevel, QuotePlan, Side
from src.risk.sizing import quote_size_per_level


def _align_price(price: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        return price
    steps = (price / increment).quantize(Decimal("1"))
    return steps * increment


def _skew_shift_price(mid: Decimal, skew_bps: float, increment: Decimal) -> Decimal:
    """Reservation price shift for inventory / portfolio (pro MM: few bps, not wide spread)."""
    shifted = mid * (Decimal("1") - Decimal(str(skew_bps)) / Decimal("10000"))
    return _align_price(shifted, increment)


def half_spread_bps(config: AppConfig, realized_vol_pct: float) -> float:
    """
    Tight pro-MM spread. realized_vol_pct is already in % (e.g. 0.13 = 0.13%).
    Old bug multiplied by 100 again -> 80-200bps spreads, zero fills.
    """
    maker_bps = config.fees.maker_pct * 100
    floor_half = maker_bps + config.fees.min_edge_bps / 2
    vol_add = config.mm.vol_spread_mult * realized_vol_pct
    dynamic = config.mm.base_half_spread_bps + vol_add
    return min(max(floor_half, dynamic), config.mm.max_half_spread_bps)


def _skew_ticks(skew_bps: float, max_ticks: int) -> int:
    """Few ticks only — pro MM skew is subtle, not hundreds of ticks."""
    return min(max_ticks, max(0, int(abs(skew_bps) / 3)))


def _touch_price(
    snapshot: MarketSnapshot,
    info: MarketInfo,
    side: Side,
    level: int,
    skew_bps: float,
    config: AppConfig,
) -> Decimal:
    """Join BBO queue — 1 tick from touch. Pro MMs compete here for fills."""
    inc = info.quote_increment
    base = config.mm.touch_offset_ticks + level * config.mm.level_spacing_ticks
    shift = _skew_ticks(skew_bps, config.mm.max_skew_ticks)

    if side == Side.BUY:
        # Long inventory -> lower bid (buy less); short -> raise bid
        offset = inc * Decimal(base + shift if skew_bps > 0 else max(1, base - shift))
        price = snapshot.best_bid - offset
        if price >= snapshot.best_ask:
            price = snapshot.best_ask - inc
        return max(price, inc)

    # Long inventory -> lower ask (sell off); short -> raise ask
    offset = inc * Decimal(max(1, base - shift) if skew_bps > 0 else base + shift)
    price = snapshot.best_ask + offset
    if price <= snapshot.best_bid:
        price = snapshot.best_bid + inc
    return price


def build_quote_plan(
    config: AppConfig,
    exchange: OndoClient,
    market: str,
    snapshot: MarketSnapshot,
    position: Position | None,
    all_positions: list[Position],
    realized_vol_pct: float,
    budget_margin: Decimal,
    max_inventory_usd: float,
) -> QuotePlan:
    info = exchange.get_market_info(market)
    if snapshot.mid_price <= 0:
        raise ValueError(f"Invalid mid for {market}")

    inv_util = inventory_utilization(position, max_inventory_usd)
    inv_skew = inventory_skew_bps(inv_util, config.mm.inventory_skew_bps)
    delta = portfolio_delta_usd(all_positions, config.portfolio.xag_beta_to_xau)
    port_skew = portfolio_skew_bps(delta, config.portfolio)
    total_skew_bps = max(-config.mm.max_skew_bps, min(config.mm.max_skew_bps, inv_skew + port_skew))

    spread = half_spread_bps(config, realized_vol_pct)

    size = quote_size_per_level(
        budget_margin,
        len(config.markets),
        config.mm.levels_per_side,
        config.max_leverage_for(market),
        snapshot.mark_price,
        info,
    )

    bid_levels: list[QuoteLevel] = []
    ask_levels: list[QuoteLevel] = []

    for level in range(config.mm.levels_per_side):
        bid_levels.append(
            QuoteLevel(
                price=_touch_price(snapshot, info, Side.BUY, level, total_skew_bps, config),
                side=Side.BUY,
                client_order_id=exchange.new_client_id(market, Side.BUY, level),
                level=level,
            )
        )
        ask_levels.append(
            QuoteLevel(
                price=_touch_price(snapshot, info, Side.SELL, level, total_skew_bps, config),
                side=Side.SELL,
                client_order_id=exchange.new_client_id(market, Side.SELL, level),
                level=level,
            )
        )

    return QuotePlan(
        market=market,
        bid_levels=bid_levels,
        ask_levels=ask_levels,
        size=size,
        half_spread_bps=spread,
        inventory_util=inv_util,
        portfolio_delta_usd=delta,
    )