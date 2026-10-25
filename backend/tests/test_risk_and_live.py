from __future__ import annotations

from datetime import date

import pandas as pd

from tradingbot.data.live import CandleBuilder, bucket_start
from tradingbot.risk import RiskManager


def _trade(rm: RiskManager, pnl: float) -> None:
    rm.on_open()
    rm.on_close(pnl)


def test_sizing_and_limits(settings) -> None:
    rm = RiskManager(settings.risk.model_copy(update={"capital": 100_000, "risk_per_trade_pct": 1,
                                                      "max_trades_per_day": 2, "max_lots": 5}))
    d = date(2025, 3, 3)
    assert rm.evaluate(d, 300).lots == 3                     # 1000 / 300
    assert rm.evaluate(d, 50).lots == 5                      # capped by max_lots
    assert not rm.evaluate(d, 2000).allowed                  # one lot too risky
    _trade(rm, -1000)
    _trade(rm, -1000)
    assert rm.evaluate(d, 300).reason == "max trades for the day"
    assert rm.evaluate(date(2025, 3, 4), 300).allowed        # resets next day
    assert rm.risk_budget < 1000                             # but equity is lower now


def test_daily_loss_limit(settings) -> None:
    rm = RiskManager(settings.risk.model_copy(update={"capital": 100_000, "max_daily_loss_pct": 2}))
    d = date(2025, 3, 3)
    rm.evaluate(d, 100)
    _trade(rm, -2500)
    assert rm.evaluate(d, 100).reason == "daily loss limit reached"


def test_candle_builder_rolls_buckets() -> None:
    tz = "Asia/Kolkata"
    b = CandleBuilder("NIFTY", 5)
    t0 = pd.Timestamp("2025-03-03 09:15:05", tz=tz)
    assert bucket_start(t0, 5) == pd.Timestamp("2025-03-03 09:15", tz=tz)
    for sec, px in [(5, 100), (60, 105), (120, 95), (290, 101)]:
        assert b.on_tick(t0 + pd.Timedelta(seconds=sec), px) is None
    done = b.on_tick(pd.Timestamp("2025-03-03 09:20:01", tz=tz), 102)
    assert done is not None
    assert (done.open, done.high, done.low, done.close) == (100, 105, 95, 101)
    assert b.flush_if_due(pd.Timestamp("2025-03-03 09:25:03", tz=tz)) is not None
