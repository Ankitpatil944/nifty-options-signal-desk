"""Turns a directional index signal into a concrete option trade and values it over time.

Value convention: a position's value per unit is sum(+premium for bought legs, -premium for sold
legs). P&L per unit is therefore exit_value - entry_value for every structure, debit or credit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from tradingbot.config import InstrumentConfig, OptionsConfig
from tradingbot.options import pricing
from tradingbot.options.expiry import pick_expiry, years_to_expiry
from tradingbot.strategies.base import Side, Signal

# (prefix, expiry, strike, right) -> live premium, or None when unavailable
QuoteFn = Callable[[str, date, float, str], float | None]


@dataclass
class OptionLeg:
    action: str      # BUY | SELL
    right: str       # CE | PE
    strike: float
    expiry: date
    premium: float   # per unit at entry
    priced_by: str   # "market" or "model"

    @property
    def sign(self) -> int:
        return 1 if self.action == "BUY" else -1

    def label(self, prefix: str) -> str:
        return f"{self.action} {prefix} {self.expiry:%d%b}".upper() + f" {self.strike:.0f} {self.right}"


@dataclass
class OptionTrade:
    structure: str                   # long_call | long_put | bull_put_spread | bear_call_spread
    prefix: str
    legs: list[OptionLeg]
    iv: float
    entry_value: float = 0.0         # per unit, see module docstring
    max_loss_per_unit: float = 0.0
    est_value_at_stop: float = 0.0
    est_value_at_target: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_credit(self) -> bool:
        return self.entry_value < 0

    def describe(self) -> str:
        return " / ".join(leg.label(self.prefix) for leg in self.legs)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for leg in d["legs"]:
            leg["expiry"] = leg["expiry"].isoformat()
        d["description"] = self.describe()
        return d


def atm_strike(spot: float, step: int) -> float:
    return float(round(spot / step) * step)


def value(trade: OptionTrade, spot: float, ts: pd.Timestamp, iv: float | None = None) -> float:
    sigma = iv or trade.iv
    return sum(
        leg.sign * pricing.price(spot, leg.strike, years_to_expiry(ts, leg.expiry), sigma, leg.right)
        for leg in trade.legs
    )


def build_trade(signal: Signal, ts: pd.Timestamp, spot: float, inst: InstrumentConfig,
                opts: OptionsConfig, quote: QuoteFn | None = None,
                expiries: list[date] | None = None) -> OptionTrade:
    step = inst.strike_step
    atm = atm_strike(spot, step)
    expiry = pick_expiry(ts, inst.expiry, inst.expiry_weekday, opts.min_days_to_expiry, expiries)
    t = years_to_expiry(ts, expiry)

    if opts.mode == "buy":
        if signal.side is Side.LONG:
            structure, specs = "long_call", [("BUY", "CE", atm + opts.buy_moneyness * step)]
        else:
            structure, specs = "long_put", [("BUY", "PE", atm - opts.buy_moneyness * step)]
    else:
        off, width = opts.sell_short_offset * step, opts.spread_width * step
        if signal.side is Side.LONG:
            structure = "bull_put_spread"
            specs = [("SELL", "PE", atm - off), ("BUY", "PE", atm - off - width)]
        else:
            structure = "bear_call_spread"
            specs = [("SELL", "CE", atm + off), ("BUY", "CE", atm + off + width)]

    legs = []
    for action, right, strike in specs:
        market = quote(inst.option_prefix, expiry, strike, right) if quote else None
        premium = market if market is not None else pricing.price(spot, strike, t, inst.iv, right)
        legs.append(OptionLeg(action, right, strike, expiry, round(premium, 2),
                              "market" if market is not None else "model"))

    # If the market priced the main leg, back out its IV so stop/target estimates are consistent.
    iv = inst.iv
    if legs[0].priced_by == "market":
        iv = pricing.implied_vol(legs[0].premium, spot, legs[0].strike, t, legs[0].right) or inst.iv

    trade = OptionTrade(structure=structure, prefix=inst.option_prefix, legs=legs, iv=iv)
    trade.entry_value = sum(leg.sign * leg.premium for leg in legs)
    if structure.endswith("spread"):
        width_pts = abs(legs[0].strike - legs[1].strike)
        trade.max_loss_per_unit = width_pts + trade.entry_value  # width - credit received
    else:
        trade.max_loss_per_unit = trade.entry_value
    trade.est_value_at_stop = value(trade, signal.stop, ts)
    trade.est_value_at_target = value(trade, signal.target, ts)
    return trade


def loss_per_unit_at_stop(trade: OptionTrade) -> float:
    """Estimated loss per unit if the underlying reaches the stop immediately (always >= 0)."""
    return max(0.0, trade.entry_value - trade.est_value_at_stop)
