import { motion } from "framer-motion";
import { FlaskConical, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { api, day, inr, num, strategyLabel, time } from "../api";
import { DrawdownChart, EquityChart } from "../components/Charts";
import { LoadingLine, Panel, Segmented, Stat, tone } from "../components/ui";
import type { BacktestResult, Meta, ResultSummary } from "../types";

const PARAM_LABELS: Record<string, string> = {
  range_minutes: "Opening range (min)",
  rr: "Reward to risk",
  stop_buffer_pct: "Stop buffer (fraction)",
  max_range_pct: "Max range (fraction)",
  fast: "Fast EMA",
  slow: "Slow EMA",
  atr_period: "ATR period",
  atr_stop: "Stop (ATR multiple)",
  band_atr: "Stretch (ATRs)",
  rsi_period: "RSI period",
  rsi_low: "RSI oversold",
  rsi_high: "RSI overbought",
};

export const paramLabel = (k: string) => PARAM_LABELS[k] ?? k.replace(/_/g, " ");

type Instrument = "options" | "futures";
type Mode = "buy" | "sell";

export function BacktestLab({ meta }: { meta: Meta }) {
  const [strategy, setStrategy] = useState(meta.strategies[0]?.name ?? "orb");
  const [symbols, setSymbols] = useState<string[]>(meta.symbols);
  const [instrument, setInstrument] = useState<Instrument>("options");
  const [mode, setMode] = useState<Mode>(meta.options.mode);
  const [params, setParams] = useState<Record<string, number>>({});
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [history, setHistory] = useState<ResultSummary[]>([]);

  const spec = meta.strategies.find((s) => s.name === strategy)!;
  useEffect(() => setParams(spec.default_params), [spec]);

  const loadHistory = () =>
    api
      .results()
      .then((r) => {
        const runs = r.filter((x) => x.kind === "backtest").slice(0, 12);
        setHistory(runs);
        return runs;
      })
      .catch(() => [] as ResultSummary[]);
  useEffect(() => {
    loadHistory().then((runs) => {
      if (runs[0]) open(runs[0].id);
    });
  }, []);

  const toggleSymbol = (s: string) =>
    setSymbols((cur) => (cur.includes(s) ? (cur.length > 1 ? cur.filter((x) => x !== s) : cur) : [...cur, s]));

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await api.backtest({
        symbols,
        strategy,
        params,
        instrument,
        option_mode: instrument === "options" ? mode : null,
        start: start || undefined,
        end: end || undefined,
      });
      setResult(r);
      loadHistory();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  async function open(id: string) {
    setError(null);
    try {
      setResult(await api.result<BacktestResult>(id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const noData = meta.datasets.length === 0;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Backtest lab</h1>
          <p>
            Replays history bar by bar through the same code the live bot runs, with Zerodha brokerage, STT, exchange
            fees, GST, stamp duty and slippage taken out of every trade.
          </p>
        </div>
      </header>

      <div className="lab">
        <div style={{ display: "grid", gap: 16 }}>
          <Panel title="Run a backtest">
            <div className="form">
              <label className="field">
                <span>Strategy</span>
                <select className="select" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                  {meta.strategies.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <p className="form-note">{spec.description}</p>

              <div className="field">
                <span>Indices</span>
                <div className="seg" role="group" aria-label="Indices">
                  {meta.symbols.map((s) => (
                    <button key={s} type="button" aria-pressed={symbols.includes(s)} onClick={() => toggleSymbol(s)}
                      style={symbols.includes(s) ? { background: "var(--raised-2)", color: "var(--text)" } : undefined}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              <div className="field">
                <span>Trade as</span>
                <Segmented label="Instrument" value={instrument} onChange={setInstrument}
                  options={[{ value: "options", label: "Options" }, { value: "futures", label: "Futures" }]} />
              </div>

              {instrument === "options" && (
                <div className="field">
                  <span>Option style</span>
                  <Segmented label="Option style" value={mode} onChange={setMode}
                    options={[{ value: "buy", label: "Buy CE / PE" }, { value: "sell", label: "Credit spreads" }]} />
                </div>
              )}

              <div className="row2">
                {Object.entries(params).map(([k, v]) => (
                  <label className="field" key={k}>
                    <span>{paramLabel(k)}</span>
                    <input className="input" type="number" step="any" value={v}
                      onChange={(e) => setParams((p) => ({ ...p, [k]: Number(e.target.value) }))} />
                  </label>
                ))}
              </div>

              <div className="row2">
                <label className="field">
                  <span>From</span>
                  <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
                </label>
                <label className="field">
                  <span>To</span>
                  <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
                </label>
              </div>

              <button className="btn primary" onClick={run} disabled={running || noData}>
                <Play size={16} /> {running ? "Running backtest" : "Run backtest"}
              </button>
              <LoadingLine active={running} />
              {noData && <p className="form-note">No history yet. Run <code>tradingbot synth</code> or <code>tradingbot download</code>.</p>}
              {error && <div className="error-box">{error}</div>}
            </div>
          </Panel>

          {history.length > 0 && (
            <Panel title="Earlier runs">
              <div className="history">
                {history.map((h) => (
                  <button key={h.id} onClick={() => open(h.id)} aria-current={result?.id === h.id}>
                    <span>{strategyLabel(h.strategy)}</span>
                    <strong className={tone(h.net_pnl)}>{inr(h.net_pnl, { sign: true })}</strong>
                    <small>
                      {h.symbols.join(" + ")}, {h.instrument === "futures" ? "futures" : h.option_mode === "sell" ? "spreads" : "options"}
                    </small>
                    <small>{h.trades ?? 0} trades</small>
                  </button>
                ))}
              </div>
            </Panel>
          )}
        </div>

        {result ? (
            <motion.div key={result.id} initial={{ y: 8 }} animate={{ y: 0 }} transition={{ duration: 0.25 }}>
              <Results result={result} capital={meta.risk.capital} />
            </motion.div>
          ) : (
            <Panel>
              <div className="empty">
                <FlaskConical size={28} color="#5b6580" />
                <h3>Pick a strategy and run it</h3>
                <p>Results show net of every charge, with the equity curve, drawdowns and each trade.</p>
              </div>
            </Panel>
          )}
      </div>
    </>
  );
}

function Results({ result, capital }: { result: BacktestResult; capital: number }) {
  const m = result.metrics;
  const req = result.request;
  if (!m.trades) {
    return (
      <Panel>
        <div className="empty">
          <h3>No trades taken</h3>
          <p>
            {Object.entries(result.skipped).map(([k, v]) => `${v} signals skipped: ${k}`).join(". ") ||
              "The strategy found no setups in this period."}
          </p>
        </div>
      </Panel>
    );
  }
  const reasons = Object.entries(m.exit_reasons ?? {});
  const maxReason = Math.max(...reasons.map(([, v]) => v), 1);
  const skipped = Object.entries(result.skipped);

  return (
    <div>
      <div className="headline">
        <span className={`big ${tone(m.net_pnl)}`}>{inr(m.net_pnl, { sign: true })}</span>
        <span className="muted">
          {num(m.return_pct)}% on {inr(capital)} over {m.trades} trades. {strategyLabel(req.strategy)} on {req.symbols.join(" and ")},{" "}
          {req.instrument === "futures" ? "as futures" : req.option_mode === "sell" ? "as credit spreads" : "buying options"}.
        </span>
      </div>

      <dl className="stats">
        <Stat label="Win rate" value={`${num(m.win_rate, 1)}%`} />
        <Stat label="Profit factor" value={num(m.profit_factor)} />
        <Stat label="Sharpe" value={num(m.sharpe)} tone={tone(m.sharpe)} />
        <Stat label="Max drawdown" value={`${num(m.max_drawdown_pct, 1)}%`} tone="neg" />
        <Stat label="Expectancy" value={inr(m.expectancy, { sign: true })} tone={tone(m.expectancy)} />
        <Stat label="Charges paid" value={inr(m.costs)} />
      </dl>

      <Panel title="Equity" aside={`${result.equity.length} trading days`}>
        <div className="chart">
          <EquityChart data={result.equity} capital={capital} />
        </div>
      </Panel>

      <div className="grid2">
        <Panel title="Drawdown">
          <div style={{ height: 180 }}>
            <DrawdownChart data={result.equity} />
          </div>
        </Panel>
        <Panel title="How trades ended">
          <div className="bars">
            {reasons.map(([k, v]) => (
              <div className="bar-row" key={k}>
                <span className="muted">{{ TARGET: "Target", STOP: "Stop", TIME: "Square-off", END: "End of data" }[k] ?? k}</span>
                <div className="meter">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${(v / maxReason) * 100}%` }}
                    style={{ background: k === "TARGET" ? "var(--long)" : k === "STOP" ? "var(--short)" : "var(--muted)" }} />
                </div>
                <span className="num">{v}</span>
              </div>
            ))}
          </div>
          <dl className="kv" style={{ marginTop: 18 }}>
            <div className="kv-row"><dt>Average win</dt><dd className="pos">{inr(m.avg_win)}</dd></div>
            <div className="kv-row"><dt>Average loss</dt><dd className="neg">{inr(m.avg_loss)}</dd></div>
            <div className="kv-row"><dt>Longest losing streak</dt><dd>{m.max_consecutive_losses}</dd></div>
            <div className="kv-row"><dt>Charges as share of gross</dt><dd>{num(m.cost_drag_pct, 1)}%</dd></div>
          </dl>
          {skipped.length > 0 && (
            <p className="form-note" style={{ marginTop: 14 }}>
              Skipped by risk rules: {skipped.map(([k, v]) => `${v} × ${k}`).join(", ")}.
            </p>
          )}
        </Panel>
      </div>

      <Panel title="Trades" aside={result.trades.length > 300 ? "Latest 300" : `${result.trades.length} trades`} className="trades-panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Index</th>
                <th>Contract</th>
                <th className="num">Entry</th>
                <th className="num">Exit</th>
                <th>Result</th>
                <th className="num">Lots</th>
                <th className="num">Charges</th>
                <th className="num">Net P&L</th>
              </tr>
            </thead>
            <tbody>
              {result.trades.slice(-300).reverse().map((t, i) => (
                <tr key={i}>
                  <td>{day(t.entry_ts)}, {time(t.entry_ts)}</td>
                  <td><span className={`tag ${t.side === "LONG" ? "long" : "short"}`}>{t.symbol}</span></td>
                  <td className="muted">{t.contract}</td>
                  <td className="num">{num(t.entry_spot, 1)}</td>
                  <td className="num">{num(t.exit_spot, 1)}</td>
                  <td className="muted">{{ TARGET: "Target", STOP: "Stop", TIME: "Square-off", END: "End" }[t.exit_reason] ?? t.exit_reason}</td>
                  <td className="num">{t.lots}</td>
                  <td className="num faint">{inr(t.costs)}</td>
                  <td className={`num ${tone(t.net_pnl) ?? ""}`}>{inr(t.net_pnl, { sign: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
