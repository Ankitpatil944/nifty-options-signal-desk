"""Rule-based expiry calendar used in backtests (live mode reads real expiries from Kite).

Exchange holidays are ignored, so a few expiries in history will be off by a day. The effect on
time-value estimates is small and is noted in the README as a known limitation.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd

EXPIRY_TIME = time(15, 30)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def candidate_expiries(after: date, kind: str, weekday: int) -> list[date]:
    if kind == "weekly":
        first = after + timedelta(days=(weekday - after.weekday()) % 7)
        return [first + timedelta(weeks=k) for k in range(6)]
    out = []
    y, m = after.year, after.month
    for _ in range(3):
        out.append(_last_weekday_of_month(y, m, weekday))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return [d for d in out if d >= after]


def years_to_expiry(ts: pd.Timestamp | datetime, expiry: date) -> float:
    ts = pd.Timestamp(ts)
    end = pd.Timestamp(datetime.combine(expiry, EXPIRY_TIME))
    if ts.tzinfo is not None:
        end = end.tz_localize(ts.tzinfo)
    return max(0.0, (end - ts).total_seconds() / (365 * 24 * 3600))


def pick_expiry(ts: pd.Timestamp, kind: str, weekday: int, min_days: float,
                available: list[date] | None = None) -> date:
    """Nearest expiry at least `min_days` away. `available` overrides the rule-based calendar."""
    choices = available or candidate_expiries(ts.date(), kind, weekday)
    for d in sorted(choices):
        if years_to_expiry(ts, d) * 365 >= min_days:
            return d
    raise ValueError(f"no expiry found after {ts}")
