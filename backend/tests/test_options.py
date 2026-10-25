from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from tradingbot.options import pricing
from tradingbot.options.expiry import candidate_expiries, pick_expiry
from tradingbot.options.mapper import atm_strike, build_trade
from tradingbot.strategies.base import Side, Signal

TS = pd.Timestamp("2025-03-03 10:00", tz="Asia/Kolkata")  # a Monday


def test_put_call_parity() -> None:
    s, k, t, v, r = 24000, 24100, 10 / 365, 0.14, pricing.RISK_FREE
    call, put = pricing.price(s, k, t, v, "CE"), pricing.price(s, k, t, v, "PE")
    assert call - put == pytest.approx(s - k * math.exp(-r * t), abs=1e-6)


def test_implied_vol_roundtrip() -> None:
    premium = pricing.price(24000, 24000, 7 / 365, 0.17, "CE")
    assert pricing.implied_vol(premium, 24000, 24000, 7 / 365, "CE") == pytest.approx(0.17, abs=1e-4)


def test_weekly_and_monthly_expiries() -> None:
    assert candidate_expiries(date(2025, 3, 3), "weekly", 1)[0] == date(2025, 3, 4)
    assert candidate_expiries(date(2025, 3, 3), "monthly", 1)[0] == date(2025, 3, 25)
    # On expiry day with too little time left, roll to the next one.
    late = pd.Timestamp("2025-03-04 14:00", tz="Asia/Kolkata")
    assert pick_expiry(late, "weekly", 1, 0.5) == date(2025, 3, 11)


def _signal(side: Side) -> Signal:
    entry = 24010.0
    stop, target = (entry - 60, entry + 120) if side is Side.LONG else (entry + 60, entry - 120)
    return Signal(TS, "NIFTY", side, entry, stop, target, "test", "test")


def test_buy_mode_maps_long_to_call_short_to_put(settings) -> None:
    inst = settings.instruments["NIFTY"]
    opts = settings.options.model_copy(update={"mode": "buy"})
    call = build_trade(_signal(Side.LONG), TS, 24010, inst, opts)
    put = build_trade(_signal(Side.SHORT), TS, 24010, inst, opts)
    assert call.structure == "long_call" and call.legs[0].right == "CE"
    assert put.structure == "long_put" and put.legs[0].right == "PE"
    assert call.legs[0].strike == atm_strike(24010, 50) == 24000
    assert call.est_value_at_target > call.entry_value > call.est_value_at_stop


def test_sell_mode_builds_defined_risk_credit_spreads(settings) -> None:
    inst = settings.instruments["NIFTY"]
    opts = settings.options.model_copy(update={"mode": "sell"})
    bull = build_trade(_signal(Side.LONG), TS, 24010, inst, opts)
    bear = build_trade(_signal(Side.SHORT), TS, 24010, inst, opts)
    assert bull.structure == "bull_put_spread"
    assert [leg.action for leg in bull.legs] == ["SELL", "BUY"]
    assert bull.legs[0].strike > bull.legs[1].strike          # hedge is further OTM
    assert bear.legs[0].strike < bear.legs[1].strike
    for trade in (bull, bear):
        assert trade.is_credit
        width = abs(trade.legs[0].strike - trade.legs[1].strike)
        assert 0 < trade.max_loss_per_unit < width
