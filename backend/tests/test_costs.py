from __future__ import annotations

import pytest

from tradingbot.backtest.costs import order_costs


def test_option_buy_has_stamp_no_stt(settings) -> None:
    c = order_costs(settings.costs, "options", "BUY", 100.0, 65, 0.0)
    turnover = 6500
    assert c.stt == 0
    assert c.stamp == pytest.approx(turnover * settings.costs.options.stamp_buy)
    assert c.brokerage == settings.costs.brokerage_per_order


def test_option_sell_has_stt_no_stamp(settings) -> None:
    c = order_costs(settings.costs, "options", "SELL", 100.0, 65, 0.0)
    assert c.stamp == 0
    assert c.stt == pytest.approx(6500 * settings.costs.options.stt_sell)


def test_gst_on_brokerage_exchange_sebi_only(settings) -> None:
    c = order_costs(settings.costs, "options", "SELL", 200.0, 30, 0.5)
    expected = settings.costs.gst * (c.brokerage + c.exchange + c.sebi)
    assert c.gst == pytest.approx(expected)
    assert c.slippage == pytest.approx(15.0)
    assert c.total == pytest.approx(c.brokerage + c.stt + c.exchange + c.sebi + c.stamp + c.gst + c.slippage)
