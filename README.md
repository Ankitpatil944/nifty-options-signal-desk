# Signal Desk

A signal engine for NIFTY and BANKNIFTY options. It backtests intraday strategies with realistic
Indian F&O costs, validates them walk-forward, and in live mode sends sized option suggestions to
Telegram and a React dashboard. **It never places orders** - you do.

```
             ┌──────────────┐     ┌────────────────┐     ┌──────────────┐
 Kite ticks ─▶ CandleBuilder ├──┐  │                │     │ Risk manager │
             └──────────────┘  ├─▶│   Strategies   ├────▶│ sizing+limits├──┐
 Replay    ─────────────────────┘  │ prepare/check  │     └──────────────┘  │
 (history)                         └───────▲────────┘                       ▼
                                           │                     ┌──────────────────┐
 Parquet store ─▶ Backtest engine ─────────┘                     │ Options mapper   │
                  (same strategy, risk,                          │ strike, expiry,  │
                   exit and cost code)                           │ premium, SL/tgt  │
                         │                                       └────────┬─────────┘
                         ▼                                                ▼
                  Metrics, walk-forward                 Telegram · SQLite journal · WebSocket
                         │                                                │
                         └──────────────▶ FastAPI ◀───────────────────────┘
                                             │
                                     React + Framer Motion
```

## What's in it

| Area | Highlights |
|---|---|
| Data | Kite historical download, chunked per Kite's per-request limits and throttled to the rate limit; Parquet store; validation and repair; synthetic generator for working without a subscription |
| Strategies | Opening range breakout, EMA trend with VWAP filter, VWAP reversion. One interface (`prepare` + `check`) shared by backtest and live |
| Backtester | Event-driven: signal on bar close, fill on next open, gaps fill at the open, ambiguous bars assume the stop. Entry window, square-off, one position per symbol |
| Costs | Brokerage, STT, NSE transaction charges, SEBI fee, stamp duty, GST, slippage, per leg and per side |
| Options | Black-Scholes pricing, weekly/monthly expiry calendar, ATM/OTM strike selection. **Buy mode**: CE for long, PE for short. **Sell mode**: bull put / bear call credit spreads (defined risk) |
| Risk | Position size from % of current equity at risk, daily loss limit, max trades per day, max open positions, max lots |
| Validation | Walk-forward optimisation with stitched out-of-sample equity |
| Live | Kite WebSocket feed or replay, Telegram suggestions and `/status /open /pnl /pause /resume`, outcome tracking with the backtester's exit rules |
| Dashboard | Live desk with signal tickets, backtest lab, walk-forward explorer, journal comparing live results with backtest expectations |
| Quality | Tests prove indicators are causal (no look-ahead) and that batch and bar-by-bar signals match; CI runs lint, tests and the frontend build |

## Setup

Requires Python 3.11+ and Node 20+.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev,kite]"
copy .env.example .env          # add Kite and Telegram credentials when you have them

cd ..\frontend
npm install
npm run build                   # the API serves the built dashboard
```

## Daily use

```powershell
cd backend
.venv\Scripts\activate

tradingbot login                # once per day: Kite tokens expire daily
tradingbot serve                # dashboard at http://127.0.0.1:8000
```

Open the dashboard, choose **Kite live**, press **Start bot**. Stop it whenever you like.
Without the dashboard: `tradingbot live --source kite` (Ctrl+C to stop).

### Without a Kite subscription

```powershell
tradingbot synth --days 500     # synthetic 1-minute history
tradingbot serve                # then use Replay on the live desk
```

### Research commands

```powershell
tradingbot download --days 365                       # real history (Kite Connect paid plan)
tradingbot backtest --strategy orb                   # options, buy mode
tradingbot backtest --strategy orb --mode sell       # credit spreads
tradingbot backtest --strategy ema_trend --instrument futures --params '{"rr": 2.5}'
tradingbot walkforward --strategy orb --train-days 120 --test-days 40
```

For frontend development with hot reload: `tradingbot serve` in one terminal and `npm run dev` in
`frontend/` (http://localhost:5173, proxied to the API).

## Telegram

1. Create a bot with @BotFather and copy the token.
2. Send your bot any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
3. Put both in `backend/.env` as `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## Configuration

Everything tunable is in `backend/config/settings.yaml`: session times, lot sizes, expiry rules,
charges, risk limits, option style (`buy` or `sell`) and strategy parameters.
**Lot sizes, expiry weekdays and statutory charges change - check them against NSE and Zerodha.**

## Design decisions

- **One code path.** Strategies, sizing, exit rules and costs are shared by backtest and live,
  so the journal can be compared like-for-like with backtest expectations.
- **No look-ahead.** Indicators are causal; signals fire on a closed bar and fill on the next
  open. `tests/test_no_lookahead.py` recomputes every indicator on truncated history and requires
  identical values.
- **Pessimistic fills.** Gaps through a level fill at the open; a bar touching both stop and target
  counts as a stop.
- **Sizing from risk, not conviction.** Lots = risk budget ÷ estimated loss per lot at the stop,
  sized off current equity.
- **Signals on the index, trades in options.** Index history is reliable and long; option premiums
  are modelled with Black-Scholes in backtests and taken from live quotes when running on Kite.
- **Synthetic data as a control.** On random-walk-like data, strategies should not show an edge
  after costs. ORB does show one on synthetic data because the generator includes all-day trend
  days, which is exactly the structure a breakout targets.

## Known limitations

- Backtested option P&L uses Black-Scholes with a constant IV per index, so IV changes
  (event days, expiry-day crush) are not captured. Treat option backtests as estimates; futures
  mode shows the raw signal edge.
- The rule-based expiry calendar ignores exchange holidays.
- Kite doesn't serve history for expired option contracts, so true historical premiums need
  another data source.
- Backtests on synthetic data show the pipeline working, not a tradable edge.

## Project layout

```
backend/
  config/settings.yaml      all tunables
  tradingbot/
    data/                   store, Kite client, synthetic data, live feeds
    strategies/             strategy interface + three strategies
    options/                pricing, expiry calendar, signal -> contract mapping
    backtest/               costs, fills, engine, metrics, walk-forward
    live/runner.py          live loop: feed -> strategy -> risk -> Telegram/journal/UI
    risk.py positions.py journal.py telegram.py api.py cli.py
  tests/
frontend/src/
  pages/                    LiveDesk, BacktestLab, WalkForward, Journal
  components/               Ticket (price ladder), charts, UI primitives
```

Not investment advice. Most retail F&O traders lose money; this tool exists to measure ideas
honestly before risking any.
