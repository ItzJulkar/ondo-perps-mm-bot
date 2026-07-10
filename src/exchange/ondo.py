import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from src.config import DEFAULT_MAX_LEVERAGE
from src.models import MarginBalance, MarketInfo, MarketSnapshot, Order, OrderType, Position, PositionDirection, QuoteLevel, Side

logger = logging.getLogger(__name__)


class OndoClient:
    def __init__(self, base_url: str, key_id: str, api_secret: str, order_prefix: str = "pmm_", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.key_id = key_id
        self.api_secret = api_secret
        self.order_prefix = order_prefix
        self.timeout = timeout
        self._session = requests.Session()

    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        payload = timestamp + method.upper() + path + body
        return hmac.new(self.api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def _headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        return {
            "ONDO-KEY-ID": self.key_id,
            "ONDO-TIMESTAMP": timestamp,
            "ONDO-SIGN": self._sign(timestamp, method, path, body),
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None,
        auth: bool = True,
    ) -> Any:
        query = "?" + urlencode(params) if params else ""
        full_path = path + query
        url = self.base_url + full_path
        body_str = json.dumps(body, separators=(",", ":")) if body is not None else ""
        headers = self._headers(method, full_path, body_str) if auth else {}

        response = self._session.request(
            method=method,
            url=url,
            headers=headers,
            data=body_str if body is not None else None,
            timeout=self.timeout,
        )

        try:
            data = response.json()
        except ValueError as exc:
            response.raise_for_status()
            raise RuntimeError(f"Non-JSON response: {response.text}") from exc

        if response.status_code >= 400 or not data.get("success", True):
            error = data.get("error", response.text)
            code = data.get("error_code", "")
            raise RuntimeError(f"Ondo API error ({response.status_code}, {code}): {error}")

        return data.get("result")

    def get_market_info(self, market: str) -> MarketInfo:
        result = self._request("GET", "/v1/markets", auth=False)
        for pair in result["perps"]["tradingPairs"]:
            if pair["market"] == market:
                return MarketInfo(
                    market=market,
                    base_increment=Decimal(pair["baseIncrement"]),
                    quote_increment=Decimal(pair["quoteIncrement"]),
                    max_leverage=DEFAULT_MAX_LEVERAGE.get(market, 20),
                )
        raise ValueError(f"Market not found: {market}")

    def get_market_snapshot(self, market: str, depth: int = 5) -> MarketSnapshot:
        marks = self._request("GET", "/v1/perps/mark_prices", auth=False)
        mark_data = marks.get(market, {})
        mark = Decimal(mark_data.get("markPrice") or mark_data.get("price", "0"))

        book = self._request("GET", "/v1/perps/depth", params={"market": market, "depth": depth}, auth=False)
        best_bid = Decimal(book["bids"][0][0]) if book.get("bids") else mark
        best_ask = Decimal(book["asks"][0][0]) if book.get("asks") else mark
        bid_vol = sum(float(b[1]) for b in book.get("bids", []))
        ask_vol = sum(float(a[1]) for a in book.get("asks", []))

        return MarketSnapshot(
            market=market,
            mark_price=mark,
            best_bid=best_bid,
            best_ask=best_ask,
            mid_price=(best_bid + best_ask) / 2,
            bid_volume=bid_vol,
            ask_volume=ask_vol,
        )

    def get_balance(self) -> MarginBalance:
        result = self._request("GET", "/v1/perps/balance")
        return MarginBalance(
            margin_balance=Decimal(result["marginBalance"]),
            available_margin=Decimal(result["availableMargin"]),
            wallet_balance=Decimal(result["walletBalance"]),
            unrealized_pnl=Decimal(result["unrealizedPnl"]),
            margin_ratio_pct=float(result.get("marginRatio", 0)) * 100,
            used_margin=Decimal(result.get("usedMargin", "0")),
            maintenance_margin=Decimal(result.get("totalMaintenanceMargin", "0")),
        )

    def get_portfolio_pnl(self) -> dict[str, Any]:
        return self._request("GET", "/v1/perps/portfolio/summary") or {}

    def set_leverage(self, market: str, leverage: int) -> None:
        self._request("POST", "/v1/perps/leverage", body={"market": market, "leverage": str(leverage)})

    def get_realized_vol_pct(self, market: str, resolution: str = "60", periods: int = 24) -> float:
        mins = int(resolution) if resolution.isdigit() else 60
        now = int(time.time())
        start = now - periods * mins * 60
        result = self._request(
            "GET",
            "/v1/perps/candles",
            params={"market": market, "resolution": resolution, "from": start, "to": now},
        )
        if not result or len(result) < 3:
            return 0.15
        closes = [float(c["close"]) for c in result]
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
        if not returns:
            return 0.15
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / len(returns)
        return max((var**0.5) * 100, 0.05)

    def get_open_orders(self, market: str) -> list[Order]:
        result = self._request("GET", "/v1/perps/orders", params={"market": market, "status": "open", "limit": 1000})
        items = result if isinstance(result, list) else result.get("orders", [])
        return [self._parse_order(item) for item in items]

    def get_bot_orders(self, market: str) -> list[Order]:
        return [o for o in self.get_open_orders(market) if o.client_order_id and o.client_order_id.startswith(self.order_prefix)]

    def get_positions(self, market: Optional[str] = None) -> list[Position]:
        result = self._request("GET", "/v1/perps/positions")
        positions = []
        for item in result or []:
            if market and item["market"] != market:
                continue
            direction = PositionDirection(item["direction"])
            qty = Decimal(item["netQuantity"])
            if direction == PositionDirection.NEUTRAL or qty == 0:
                continue
            positions.append(
                Position(
                    market=item["market"],
                    direction=direction,
                    net_quantity=qty,
                    average_entry_price=Decimal(item["averageEntryPrice"]),
                    unrealized_pnl=Decimal(item["unrealizedPnl"]),
                    mark_price=Decimal(item["markPrice"]),
                )
            )
        return positions

    def place_batch_quotes(self, market: str, levels: list[QuoteLevel], size: Decimal) -> list[Order]:
        if not levels:
            return []
        orders_body = []
        for level in levels:
            orders_body.append(
                {
                    "side": level.side.value,
                    "market": market,
                    "price": str(level.price),
                    "size": str(size),
                    "type": "limit",
                    "timeInForce": "GTC",
                    "postOnly": True,
                    "clientOrderId": level.client_order_id,
                }
            )
        result = self._request("POST", "/v1/perps/orders/batch", body={"orders": orders_body}) or {}
        placed = [self._parse_order(item) for item in result.get("addedOrders") or []]
        for failed in result.get("failedOrders") or []:
            logger.warning("[%s] Batch order failed: %s", market, failed.get("error", failed))
        return placed

    def cancel_order(self, market: str, order_id: str) -> None:
        self._request("DELETE", f"/v1/perps/orders/{order_id}", params={"market": market})

    def cancel_bot_orders(self, market: str) -> int:
        cancelled = 0
        for order in self.get_bot_orders(market):
            self.cancel_order(market, order.order_id)
            cancelled += 1
        return cancelled

    def close_position_market(self, market: str, side: Side, size: Decimal) -> Order:
        result = self._request(
            "POST",
            "/v1/perps/orders",
            body={"side": side.value, "market": market, "size": str(size), "type": "market", "reduceOnly": True},
        )
        return self._parse_order(result)

    def new_client_id(self, market: str, side: Side, level: int) -> str:
        slug = market.replace("-", "_").replace(".", "_")
        return f"{self.order_prefix}{slug}_{side.value}_{level}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _parse_order(item: dict[str, Any]) -> Order:
        created_at = None
        if raw := item.get("createdAt"):
            created_at = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        return Order(
            order_id=item["orderId"],
            client_order_id=item.get("clientOrderId"),
            market=item["market"],
            side=Side(item["side"]),
            price=Decimal(item.get("price") or "0"),
            size=Decimal(item["size"]),
            status=item["status"],
            filled_size=Decimal(item.get("filledSize", "0")),
            order_type=OrderType(item.get("type", "limit")),
            created_at=created_at,
        )