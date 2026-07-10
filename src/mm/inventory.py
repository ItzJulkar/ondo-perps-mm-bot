from src.models import Position


def inventory_utilization(position: Position | None, max_inventory_usd: float) -> float:
    if not position or max_inventory_usd <= 0:
        return 0.0
    sign = 1.0 if position.direction.value == "long" else -1.0
    return max(-1.0, min(1.0, sign * float(position.notional_value) / max_inventory_usd))


def inventory_skew_bps(util: float, skew_bps: float) -> float:
    """
    Classic MM inventory skew: long inventory -> lower reservation (encourage sells).
    """
    return util * skew_bps