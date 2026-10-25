"""Black-Scholes pricing for European index options (NIFTY/BANKNIFTY options are European)."""

from __future__ import annotations

import math

RISK_FREE = 0.065
MIN_T = 1 / (365 * 24 * 60)  # one minute, avoids division by zero at expiry


def _cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _d1_d2(spot: float, strike: float, t: float, sigma: float, r: float) -> tuple[float, float]:
    t = max(t, MIN_T)
    vol_t = sigma * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma**2) * t) / vol_t
    return d1, d1 - vol_t


def price(spot: float, strike: float, t: float, sigma: float, right: str, r: float = RISK_FREE) -> float:
    if t <= 0:
        return max(0.0, spot - strike) if right == "CE" else max(0.0, strike - spot)
    d1, d2 = _d1_d2(spot, strike, t, sigma, r)
    disc = math.exp(-r * max(t, MIN_T))
    if right == "CE":
        return spot * _cdf(d1) - strike * disc * _cdf(d2)
    return strike * disc * _cdf(-d2) - spot * _cdf(-d1)


def delta(spot: float, strike: float, t: float, sigma: float, right: str, r: float = RISK_FREE) -> float:
    d1, _ = _d1_d2(spot, strike, t, sigma, r)
    return _cdf(d1) if right == "CE" else _cdf(d1) - 1


def implied_vol(premium: float, spot: float, strike: float, t: float, right: str,
                r: float = RISK_FREE) -> float | None:
    """Bisection IV solve; returns None when the premium is outside the no-arbitrage range."""
    lo, hi = 0.01, 3.0
    if not price(spot, strike, t, lo, right, r) <= premium <= price(spot, strike, t, hi, right, r):
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if price(spot, strike, t, mid, right, r) < premium:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
