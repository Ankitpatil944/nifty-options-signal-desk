from __future__ import annotations

import pandas as pd

from tests.conftest import make_bars
from tradingbot.backtest import engine
from tradingbot.backtest.fills import check_exit
from tradingbot.strategies.base import Side, Signal, Strategy


def test_exit_prefers_stop_when_both_touched() -> None:
    assert check_exit(Side.LONG, 99, 105, 100, 106, 98) == ("STOP", 99)
    assert check_exit(Side.SHORT, 101, 95, 100, 102, 94) == ("STOP", 101)


def test_gap_through_stop_fills_at_open() -> None:
    assert check_exit(Side.LONG, 99, 105, 97, 98, 96) == ("STOP", 97)
    assert check_exit(Side.SHORT, 101, 95, 94, 96, 93) == ("TARGET", 94)


class BuyAt(Strategy):
    """Test strategy: go long at one specific bar."""
    name = "buy_at"
    label = description = "test"
    default_params = {"bar": 2.0, "stop": 10.0, "target": 20.0}
    param_grid: dict = {}

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def check(self, df: pd.DataFrame, i: int, symbol: str) -> Signal | None:
        if i != int(self.p("bar")):
            return None
        c = df["close"].iat[i]
        return self._signal(df, i, symbol, Side.LONG, c - self.p("stop"), c + self.p("target"), "test")


def _run(settings, rows) -> engine.BacktestResult:
    bars = make_bars(rows, "2025-03-03 09:15")
    req = engine.BacktestRequest(["NIFTY"], "buy_at", instrument="futures")
    cfg = settings.model_copy(deep=True)
    cfg.risk.capital = 10_000_000  # large enough that one futures lot is always allowed
    return engine.run(cfg, BuyAt(), {"NIFTY": bars}, req)


def test_fills_next_open_and_hits_target(settings) -> None:
    rows = [(1000, 1001, 999, 1000)] * 3 + [(1002, 1005, 1001, 1004), (1004, 1030, 1003, 1025)]
    res = _run(settings, [*rows, *[(1025, 1026, 1024, 1025)] * 10])
    t = res.trades.iloc[0]
    assert t["entry_spot"] == 1002          # next bar's open, not the signal close
    assert t["exit_reason"] == "TARGET"
    assert t["exit_spot"] == 1020           # signal close 1000 + 20
    assert t["gross_pnl"] == (1020 - 1002) * settings.instruments["NIFTY"].lot_size * t["lots"]
    assert t["net_pnl"] < t["gross_pnl"]     # costs applied


def test_signal_bar_cannot_exit_itself(settings) -> None:
    # The signal bar's own low is far below the stop; the trade must not see it.
    rows = [(1000, 1001, 999, 1000)] * 2 + [(1000, 1001, 900, 1000)] + [(1000, 1001, 999, 1000)] * 10
    res = _run(settings, rows)
    assert res.trades.iloc[0]["exit_reason"] == "END"


def test_entries_only_inside_window(settings) -> None:
    rows = [(1000, 1001, 999, 1000)] * 80
    # bar 60 = 14:15, outside the 09:20-12:00 entry window
    bars = make_bars(rows)
    cfg = settings.model_copy(deep=True)
    cfg.risk.capital = 10_000_000
    res = engine.run(cfg, BuyAt(bar=60), {"NIFTY": bars},
                     engine.BacktestRequest(["NIFTY"], "buy_at", instrument="futures"))
    assert res.trades.empty
