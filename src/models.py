from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


class PositionDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class MarketInfo:
    market: str
    base_increment: Decimal
    quote_increment: Decimal
    max_leverage: int = 20


@dataclass
class MarginBalance:
    margin_balance: Decimal
    available_margin: Decimal
    wallet_balance: Decimal
    unrealized_pnl: Decimal
    margin_ratio_pct: float = 0.0
    used_margin: Decimal = Decimal("0")
    maintenance_margin: Decimal = Decimal("0")


@dataclass
class MarketSnapshot:
    market: str
    mark_price: Decimal
    best_bid: Decimal
    best_ask: Decimal
    mid_price: Decimal
    bid_volume: float = 0.0
    ask_volume: float = 0.0


@dataclass
class QuoteLevel:
    price: Decimal
    side: Side
    client_order_id: str
    level: int = 0


@dataclass
class Order:
    order_id: str
    client_order_id: Optional[str]
    market: str
    side: Side
    price: Decimal
    size: Decimal
    status: str
    filled_size: Decimal
    order_type: OrderType
    created_at: Optional[float] = None


@dataclass
class Position:
    market: str
    direction: PositionDirection
    net_quantity: Decimal
    average_entry_price: Decimal
    unrealized_pnl: Decimal
    mark_price: Decimal

    @property
    def signed_qty(self) -> Decimal:
        if self.direction == PositionDirection.SHORT:
            return -self.net_quantity
        return self.net_quantity

    @property
    def notional_value(self) -> Decimal:
        return self.net_quantity * self.mark_price


@dataclass
class QuotePlan:
    market: str
    bid_levels: list[QuoteLevel]
    ask_levels: list[QuoteLevel]
    size: Decimal
    half_spread_bps: float
    inventory_util: float
    portfolio_delta_usd: float