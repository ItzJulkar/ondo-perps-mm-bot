"""Quick API check — balance, BBO, and sample quote prices."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config
from src.exchange.ondo import OndoClient
from src.mm.quoter import build_quote_plan
from src.mm.risk import RiskManager
from decimal import Decimal


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config_path = root / "config.yaml"
    if not config_path.exists():
        raise SystemExit("Copy config.example.yaml to config.yaml first.")

    config = load_config(config_path)
    if not config.key_id or not config.api_secret:
        raise SystemExit("Missing ONDO_KEY_ID / ONDO_API_SECRET in .env")

    client = OndoClient(
        config.api_base_url,
        config.key_id,
        config.api_secret,
        order_prefix=config.bot.order_prefix,
    )
    balance = client.get_balance()
    risk = RiskManager(config)
    budget = Decimal(str(risk.mm_budget_margin(balance)))

    print("Ondo Perps MM — connection OK")
    print(f"  Equity:          ${balance.margin_balance}")
    print(f"  Available:       ${balance.available_margin}")
    print(f"  Margin ratio:    {balance.margin_ratio_pct:.2f}%")
    print(f"  MM budget:       ${budget:.2f} ({config.mm.margin_budget_pct}% of available)")

    positions = client.get_positions()
    for market in config.markets:
        snap = client.get_market_snapshot(market)
        vol = client.get_realized_vol_pct(market)
        pos = next((p for p in positions if p.market == market), None)
        plan = build_quote_plan(
            config, client, market, snap, pos, positions, vol, budget,
            config.portfolio.max_portfolio_delta_usd,
        )
        print(f"\n  {market}")
        print(f"    BBO:       {snap.best_bid} / {snap.best_ask}")
        print(f"    MM bid:    {plan.bid_levels[0].price}")
        print(f"    MM ask:    {plan.ask_levels[0].price}")
        print(f"    Size:      {plan.size}")


if __name__ == "__main__":
    main()