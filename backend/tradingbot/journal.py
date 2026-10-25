"""SQLite journal of every live suggestion and how it played out.

Each signal is tracked against subsequent candles with the same exit rules the backtester uses,
which is what makes the live-vs-backtest comparison meaningful.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    source        TEXT NOT NULL,          -- kite | replay
    symbol        TEXT NOT NULL,
    strategy      TEXT NOT NULL,
    side          TEXT NOT NULL,
    entry         REAL NOT NULL,
    stop          REAL NOT NULL,
    target        REAL NOT NULL,
    reason        TEXT,
    confidence    REAL,
    contract      TEXT,
    structure     TEXT,
    lots          INTEGER,
    qty           INTEGER,
    entry_value   REAL,                   -- option position value per unit at entry
    value_at_stop REAL,
    value_at_target REAL,
    option_json   TEXT,
    status        TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN | TARGET | STOP | TIME
    exit_at       TEXT,
    exit_spot     REAL,
    exit_value    REAL,
    pnl           REAL                    -- estimated net INR, after costs
);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
"""


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def add(self, row: dict[str, Any]) -> int:
        row = dict(row)
        if "option" in row:
            row["option_json"] = json.dumps(row.pop("option"))
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cur = self.conn.execute(f"INSERT INTO signals ({cols}) VALUES ({marks})", list(row.values()))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def close(self, signal_id: int, status: str, exit_at: str, exit_spot: float, exit_value: float,
              pnl: float) -> None:
        self.conn.execute(
            "UPDATE signals SET status=?, exit_at=?, exit_spot=?, exit_value=?, pnl=? WHERE id=?",
            (status, exit_at, exit_spot, exit_value, pnl, signal_id),
        )
        self.conn.commit()

    def get(self, signal_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
        return _row(row) if row else None

    def recent(self, limit: int = 100, source: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM signals", []
        if source:
            sql, args = sql + " WHERE source=?", [source]
        rows = self.conn.execute(sql + " ORDER BY id DESC LIMIT ?", [*args, limit]).fetchall()
        return [_row(r) for r in rows]

    def open_signals(self) -> list[dict[str, Any]]:
        return [_row(r) for r in self.conn.execute("SELECT * FROM signals WHERE status='OPEN'").fetchall()]

    def stats(self, source: str | None = None) -> dict[str, Any]:
        where = "WHERE status != 'OPEN'" + (" AND source=?" if source else "")
        args = [source] if source else []
        row = self.conn.execute(
            f"""SELECT COUNT(*) n, COALESCE(SUM(pnl),0) pnl,
                       COALESCE(AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0.0 END),0) win_rate,
                       COALESCE(AVG(pnl),0) expectancy
                FROM signals {where}""", args).fetchone()
        by_strategy = self.conn.execute(
            f"""SELECT strategy, COUNT(*) n, COALESCE(SUM(pnl),0) pnl,
                       AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0.0 END) win_rate
                FROM signals {where} GROUP BY strategy""", args).fetchall()
        return {
            "closed": row["n"], "net_pnl": round(row["pnl"], 2),
            "win_rate": round(row["win_rate"] * 100, 1), "expectancy": round(row["expectancy"], 2),
            "by_strategy": [dict(r) for r in by_strategy],
        }


def _row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    raw = d.pop("option_json", None)
    d["option"] = json.loads(raw) if raw else None
    return d
