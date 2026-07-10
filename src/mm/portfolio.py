from decimal import Decimal

from src.config import PortfolioConfig
from src.models import Position


def portfolio_delta_usd(positions: list[Position], xag_beta: float) -> float:
    """
    Net metals exposure in XAU-equivalent USD.
    Long XAU + beta-weighted long XAG = net long precious metals book.
    """
    delta = 0.0
    for pos in positions:
        sign = 1.0 if pos.direction.value == "long" else -1.0
        notional = float(pos.notional_value)
        if "XAG" in pos.market:
            notional *= xag_beta
        delta += sign * notional
    return delta


def portfolio_skew_bps(delta_usd: float, config: PortfolioConfig) -> float:
    """Shift reservation price down when net long, up when net short."""
    if not config.hedge_enabled or config.max_portfolio_delta_usd <= 0:
        return 0.0
    util = max(-1.0, min(1.0, delta_usd / config.max_portfolio_delta_usd))
    return util * config.portfolio_skew_bps