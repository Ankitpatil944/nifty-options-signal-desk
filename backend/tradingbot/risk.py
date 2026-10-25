"""Position sizing and session-level guard rails, shared by the backtester and the live runner."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from tradingbot.config import RiskConfig


@dataclass
class Decision:
    allowed: bool
    lots: int = 0
    reason: str = ""


@dataclass
class RiskManager:
    cfg: RiskConfig
    day: date | None = None
    realised_today: float = 0.0
    trades_today: int = 0
    open_positions: int = 0
    paused: bool = False
    history: list[float] = field(default_factory=list)

    @property
    def equity(self) -> float:
        return self.cfg.capital + sum(self.history)

    @property
    def daily_loss_limit(self) -> float:
        return self.equity * self.cfg.max_daily_loss_pct / 100

    @property
    def risk_budget(self) -> float:
        """Sized off current equity, so risk shrinks after losses and grows after gains."""
        return max(0.0, self.equity) * self.cfg.risk_per_trade_pct / 100

    def roll(self, today: date) -> None:
        if self.day != today:
            self.day = today
            self.realised_today = 0.0
            self.trades_today = 0

    def size(self, loss_per_lot: float) -> int:
        if loss_per_lot <= 0:
            return 0
        return min(self.cfg.max_lots, math.floor(self.risk_budget / loss_per_lot))

    def evaluate(self, today: date, loss_per_lot: float) -> Decision:
        self.roll(today)
        if self.paused:
            return Decision(False, reason="paused")
        if self.realised_today <= -self.daily_loss_limit:
            return Decision(False, reason="daily loss limit reached")
        if self.trades_today >= self.cfg.max_trades_per_day:
            return Decision(False, reason="max trades for the day")
        if self.open_positions >= self.cfg.max_open_positions:
            return Decision(False, reason="max open positions")
        lots = self.size(loss_per_lot)
        if lots < 1:
            return Decision(False, reason="one lot risks more than the per-trade budget")
        return Decision(True, lots=lots)

    def on_open(self) -> None:
        self.trades_today += 1
        self.open_positions += 1

    def on_close(self, pnl: float) -> None:
        self.open_positions = max(0, self.open_positions - 1)
        self.realised_today += pnl
        self.history.append(pnl)

    def snapshot(self) -> dict[str, object]:
        return {
            "day": self.day.isoformat() if self.day else None,
            "realised_today": round(self.realised_today, 2),
            "daily_loss_limit": round(self.daily_loss_limit, 2),
            "trades_today": self.trades_today,
            "max_trades_per_day": self.cfg.max_trades_per_day,
            "open_positions": self.open_positions,
            "paused": self.paused,
            "risk_per_trade": round(self.risk_budget, 2),
            "equity": round(self.equity, 2),
        }
