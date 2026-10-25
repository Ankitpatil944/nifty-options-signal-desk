"""Indian F&O transaction costs: brokerage, STT, exchange charges, SEBI fee, stamp duty, GST, slippage."""

from __future__ import annotations

from dataclasses import dataclass, fields

from tradingbot.config import CostConfig


@dataclass
class CostBreakdown:
    brokerage: float = 0.0
    stt: float = 0.0
    exchange: float = 0.0
    sebi: float = 0.0
    stamp: float = 0.0
    gst: float = 0.0
    slippage: float = 0.0

    @property
    def total(self) -> float:
        return sum(getattr(self, f.name) for f in fields(self))

    def __add__(self, other: CostBreakdown) -> CostBreakdown:
        return CostBreakdown(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))

    def to_dict(self) -> dict[str, float]:
        d = {f.name: round(getattr(self, f.name), 2) for f in fields(self)}
        d["total"] = round(self.total, 2)
        return d


def order_costs(cfg: CostConfig, kind: str, action: str, price: float, qty: int,
                slippage_per_unit: float) -> CostBreakdown:
    """Costs of one executed order. kind is "options" (price = premium) or "futures"."""
    turnover = abs(price) * qty
    rates = cfg.options if kind == "options" else cfg.futures
    c = CostBreakdown(
        brokerage=cfg.brokerage_per_order if qty > 0 else 0.0,
        stt=turnover * rates.stt_sell if action == "SELL" else 0.0,
        exchange=turnover * rates.exchange_txn,
        sebi=turnover * cfg.sebi_fee,
        stamp=turnover * rates.stamp_buy if action == "BUY" else 0.0,
        slippage=slippage_per_unit * qty,
    )
    c.gst = cfg.gst * (c.brokerage + c.exchange + c.sebi)
    return c
