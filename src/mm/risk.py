from dataclasses import dataclass

from src.config import AppConfig
from src.models import MarginBalance


@dataclass
class RiskState:
    ok: bool
    reason: str


class RiskManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self._session_start_equity: float | None = None

    def check(self, balance: MarginBalance, max_vol_pct: float) -> RiskState:
        equity = float(balance.margin_balance)

        if self._session_start_equity is None:
            self._session_start_equity = equity

        session_pnl = equity - self._session_start_equity
        if session_pnl <= -self.config.risk.daily_loss_limit_usd:
            return RiskState(False, f"session loss ${abs(session_pnl):.2f} exceeds limit")

        if not self.config.risk.shared_account_mode and balance.margin_ratio_pct > self.config.risk.max_margin_ratio_pct:
            return RiskState(False, f"margin ratio {balance.margin_ratio_pct:.1f}% too high")

        if float(balance.available_margin) < self.config.risk.min_available_margin_usd:
            return RiskState(False, f"available margin ${balance.available_margin} too low")

        if max_vol_pct > self.config.risk.pause_on_vol_pct:
            return RiskState(False, f"volatility {max_vol_pct:.2f}% too high")

        return RiskState(True, "ok")

    def mm_budget_margin(self, balance: MarginBalance) -> float:
        return float(balance.available_margin) * (self.config.mm.margin_budget_pct / 100)