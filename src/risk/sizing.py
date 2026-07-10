from decimal import Decimal, ROUND_DOWN

from src.models import MarketInfo


def align_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        return value
    steps = (value / increment).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return steps * increment


def quote_size_per_level(
    budget_margin: Decimal,
    markets: int,
    levels_per_side: int,
    leverage: int,
    price: Decimal,
    market_info: MarketInfo,
) -> Decimal:
    """Split MM margin budget across markets and both sides."""
    sides = 2
    levels = max(levels_per_side, 1)
    slots = Decimal(markets * sides * levels)
    if slots <= 0 or price <= 0:
        return market_info.base_increment

    per_slot_margin = budget_margin / slots
    notional = per_slot_margin * Decimal(leverage)
    raw = notional / price
    size = align_to_increment(raw, market_info.base_increment)
    return max(size, market_info.base_increment)