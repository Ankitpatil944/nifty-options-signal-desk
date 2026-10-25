"""How a signal becomes a sized position, and what that position is worth later.

Two instruments are supported:
  futures - index points x lot size; a clean read on the raw signal edge
  options - the option structure from options.mapper (buy CE/PE or a credit spread)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from tradingbot.backtest.costs import CostBreakdown, order_costs
from tradingbot.config import Settings
from tradingbot.options import mapper, pricing
from tradingbot.options.expiry import years_to_expiry
from tradingbot.strategies.base import Signal

InstrumentKind = Literal["futures", "options"]


@dataclass
class Position:
    signal: Signal
    instrument: InstrumentKind
    entry_ts: pd.Timestamp
    entry_spot: float
    lot_size: int
    option: mapper.OptionTrade | None = None
    lots: int = 0
    leg_entry_prices: list[float] = field(default_factory=list)

    @property
    def qty(self) -> int:
        return self.lots * self.lot_size

    @property
    def entry_value(self) -> float:
        if self.option is None:
            return self.signal.side.sign * self.entry_spot
        return self.option.entry_value

    def loss_per_lot_at_stop(self) -> float:
        if self.option is None:
            return abs(self.entry_spot - self.signal.stop) * self.lot_size
        per_unit = mapper.loss_per_unit_at_stop(self.option)
        # Never size a defined-risk structure on less than its worst case.
        if self.option.structure.endswith("spread"):
            per_unit = max(per_unit, 0.5 * self.option.max_loss_per_unit)
        return per_unit * self.lot_size

    def leg_prices_at(self, spot: float, ts: pd.Timestamp) -> list[float]:
        if self.option is None:
            return [spot]
        return [pricing.price(spot, leg.strike, years_to_expiry(ts, leg.expiry), self.option.iv, leg.right)
                for leg in self.option.legs]

    def value_at(self, spot: float, ts: pd.Timestamp) -> float:
        if self.option is None:
            return self.signal.side.sign * spot
        return mapper.value(self.option, spot, ts)

    def costs(self, settings: Settings, exit_prices: list[float]) -> CostBreakdown:
        cfg = settings.costs
        total = CostBreakdown()
        if self.option is None:
            slip = settings.instruments[self.signal.symbol].slippage_points
            entry_action = "BUY" if self.signal.side.sign > 0 else "SELL"
            exit_action = "SELL" if entry_action == "BUY" else "BUY"
            total += order_costs(cfg, "futures", entry_action, self.entry_spot, self.qty, slip)
            total += order_costs(cfg, "futures", exit_action, exit_prices[0], self.qty, slip)
            return total
        slip = cfg.options.slippage_per_unit
        for leg, entry_px, exit_px in zip(self.option.legs, self.leg_entry_prices, exit_prices, strict=True):
            exit_action = "SELL" if leg.action == "BUY" else "BUY"
            total += order_costs(cfg, "options", leg.action, entry_px, self.qty, slip)
            total += order_costs(cfg, "options", exit_action, exit_px, self.qty, slip)
        return total


def open_position(signal: Signal, ts: pd.Timestamp, spot: float, settings: Settings,
                  instrument: InstrumentKind, quote: mapper.QuoteFn | None = None,
                  expiries: list | None = None, option_mode: str | None = None) -> Position:
    inst = settings.instruments[signal.symbol]
    pos = Position(signal=signal, instrument=instrument, entry_ts=ts, entry_spot=spot, lot_size=inst.lot_size)
    if instrument == "options":
        opts = settings.options if option_mode is None else settings.options.model_copy(
            update={"mode": option_mode})
        pos.option = mapper.build_trade(signal, ts, spot, inst, opts, quote, expiries)
        pos.leg_entry_prices = [leg.premium for leg in pos.option.legs]
    else:
        pos.leg_entry_prices = [spot]
    return pos
