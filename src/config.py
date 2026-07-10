import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

COMMODITY_MARKETS = ("XAU-USD.P", "XAG-USD.P")
DEFAULT_MAX_LEVERAGE = {"XAU-USD.P": 20, "XAG-USD.P": 20}


@dataclass
class MmConfig:
    touch_offset_ticks: int
    base_half_spread_bps: float
    max_half_spread_bps: float
    vol_spread_mult: float
    inventory_skew_bps: float
    max_skew_bps: float
    max_skew_ticks: int
    levels_per_side: int
    level_spacing_ticks: int
    quote_refresh_sec: float
    margin_budget_pct: float


@dataclass
class PortfolioConfig:
    hedge_enabled: bool
    xag_beta_to_xau: float
    max_portfolio_delta_usd: float
    portfolio_skew_bps: float


@dataclass
class RiskConfig:
    shared_account_mode: bool
    max_margin_ratio_pct: float
    daily_loss_limit_usd: float
    min_available_margin_usd: float
    pause_on_vol_pct: float


@dataclass
class FeeConfig:
    maker_pct: float
    min_edge_bps: float


@dataclass
class BotConfig:
    poll_interval_sec: float
    dry_run: bool
    log_level: str
    order_prefix: str


@dataclass
class AppConfig:
    markets: list[str]
    api_base_url: str
    leverage: int
    mm: MmConfig
    portfolio: PortfolioConfig
    risk: RiskConfig
    fees: FeeConfig
    bot: BotConfig
    key_id: Optional[str]
    api_secret: Optional[str]

    def max_leverage_for(self, market: str) -> int:
        return DEFAULT_MAX_LEVERAGE.get(market, self.leverage)


def _load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    load_dotenv(root.parent / "ondo-grid-bot" / ".env")


def load_config(path: str | Path) -> AppConfig:
    _load_env()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    mm = raw.get("mm", {})
    portfolio = raw.get("portfolio", {})
    risk = raw.get("risk", {})
    fees = raw.get("fees", {})
    bot = raw.get("bot", {})

    return AppConfig(
        markets=list(raw.get("markets", COMMODITY_MARKETS)),
        api_base_url=raw.get("api", {}).get("base_url", "https://api.ondoperps.xyz"),
        leverage=int(raw.get("leverage", 20)),
        mm=MmConfig(
            touch_offset_ticks=int(mm.get("touch_offset_ticks", 1)),
            base_half_spread_bps=float(mm.get("base_half_spread_bps", 3)),
            max_half_spread_bps=float(mm.get("max_half_spread_bps", 10)),
            vol_spread_mult=float(mm.get("vol_spread_mult", 0.8)),
            inventory_skew_bps=float(mm.get("inventory_skew_bps", 8)),
            max_skew_bps=float(mm.get("max_skew_bps", 15)),
            max_skew_ticks=int(mm.get("max_skew_ticks", 3)),
            levels_per_side=int(mm.get("levels_per_side", 1)),
            level_spacing_ticks=int(mm.get("level_spacing_ticks", 2)),
            quote_refresh_sec=float(mm.get("quote_refresh_sec", 8)),
            margin_budget_pct=float(mm.get("margin_budget_pct", 40)),
        ),
        portfolio=PortfolioConfig(
            hedge_enabled=bool(portfolio.get("hedge_enabled", True)),
            xag_beta_to_xau=float(portfolio.get("xag_beta_to_xau", 0.75)),
            max_portfolio_delta_usd=float(portfolio.get("max_portfolio_delta_usd", 18)),
            portfolio_skew_bps=float(portfolio.get("portfolio_skew_bps", 3)),
        ),
        risk=RiskConfig(
            shared_account_mode=bool(risk.get("shared_account_mode", True)),
            max_margin_ratio_pct=float(risk.get("max_margin_ratio_pct", 35)),
            daily_loss_limit_usd=float(risk.get("daily_loss_limit_usd", 0.75)),
            min_available_margin_usd=float(risk.get("min_available_margin_usd", 0.50)),
            pause_on_vol_pct=float(risk.get("pause_on_vol_pct", 0.80)),
        ),
        fees=FeeConfig(
            maker_pct=float(fees.get("maker_pct", 0.01)),
            min_edge_bps=float(fees.get("min_edge_bps", 2)),
        ),
        bot=BotConfig(
            poll_interval_sec=float(bot.get("poll_interval_sec", 2)),
            dry_run=bool(bot.get("dry_run", True)),
            log_level=str(bot.get("log_level", "INFO")),
            order_prefix=str(bot.get("order_prefix", "pmm_")),
        ),
        key_id=os.getenv("ONDO_KEY_ID"),
        api_secret=os.getenv("ONDO_API_SECRET"),
    )