import { motion } from "framer-motion";
import { Play, Route } from "lucide-react";
import { useEffect, useState } from "react";
import { api, day, inr, num, strategyLabel } from "../api";
import { EquityChart } from "../components/Charts";
import { LoadingLine, Panel, Segmented, Stat, tone } from "../components/ui";
import type { Meta, ResultSummary, WalkForwardResult } from "../types";
import { paramLabel } from "./BacktestLab";

export function WalkForward({ meta }: { meta: Meta }) {
  const [strategy, setStrategy] = useState(meta.strategies[0]?.name ?? "orb");
  const [trainDays, setTrainDays] = useState(120);
  const [testDays, setTestDays] = useState(40);
  const [objective, setObjective] = useState<"sharpe" | "net_pnl" | "profit_factor">("sharpe");
  const [mode, setMode] = useState<"buy" | "sell">(meta.options.mode);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<WalkForwardResult | null>(null);
  const [history, setHistory] = useState<ResultSummary[]>([]);

  const spec = meta.strategies.find((s) => s.name === strategy)!;
  const gridSize = Object.values(spec.param_grid).reduce((n, v) => n * v.length, 1);

  useEffect(() => {
    api
      .results()
      .then((r) => {
        const wf = r.filter((x) => x.kind === "walkforward");
        setHistory(wf.slice(0, 10));
        if (wf[0]) api.result<WalkForwardResult>(wf[0].id).then(setResult).catch(() => undefined);
      })
      .catch(() => undefined);
  }, []);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await api.walkforward({
        symbols: meta.symbols,
        strategy,
        train_days: trainDays,
        test_days: testDays,
        objective,
        instrument: "options",
        option_mode: mode,
      });
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Walk-forward</h1>
          <p>
            Tunes parameters on one stretch of history, then trades the next stretch with them unchanged, and rolls forward.
            The stitched test periods are an out-of-sample record that a single backtest can't give you.
          </p>
        </div>
      </header>

      <div className="lab">
        <div style={{ display: "grid", gap: 16 }}>
          <Panel title="Set up a run">
            <div className="form">
              <label className="field">
                <span>Strategy</span>
                <select className="select" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                  {meta.strategies.map((s) => (
                    <option key={s.name} value={s.name}>{s.label}</option>
                  ))}
                </select>
              </label>
              <p className="form-note">
                Tries {gridSize} parameter combinations per window: {Object.entries(spec.param_grid).map(([k, v]) => `${paramLabel(k).toLowerCase()} ${v.join("/")}`).join(", ")}.
              </p>
              <div className="row2">
                <label className="field">
                  <span>Train days</span>
                  <input className="input" type="number" min={20} value={trainDays} onChange={(e) => setTrainDays(Number(e.target.value))} />
                </label>
                <label className="field">
                  <span>Test days</span>
                  <input className="input" type="number" min={5} value={testDays} onChange={(e) => setTestDays(Number(e.target.value))} />
                </label>
              </div>
              <div className="field">
                <span>Pick the winner by</span>
                <Segmented label="Objective" value={objective} onChange={setObjective}
                  options={[{ value: "sharpe", label: "Sharpe" }, { value: "net_pnl", label: "Net P&L" }, { value: "profit_factor", label: "Profit factor" }]} />
              </div>
              <div className="field">
                <span>Option style</span>
                <Segmented label="Option style" value={mode} onChange={setMode}
                  options={[{ value: "buy", label: "Buy CE / PE" }, { value: "sell", label: "Credit spreads" }]} />
              </div>
              <button className="btn primary" onClick={run} disabled={running}>
                <Play size={16} /> {running ? "Running walk-forward" : "Run walk-forward"}
              </button>
              <LoadingLine active={running} />
              {running && <p className="form-note">This runs the grid once per window, so it can take a minute.</p>}
              {error && <div className="error-box">{error}</div>}
            </div>
          </Panel>

          {history.length > 0 && (
            <Panel title="Earlier runs">
              <div className="history">
                {history.map((h) => (
                  <button key={h.id} aria-current={result?.id === h.id}
                    onClick={() => api.result<WalkForwardResult>(h.id).then(setResult).catch((e) => setError(e.message))}>
                    <span>{strategyLabel(h.strategy)}</span>
                    <strong className={tone(h.net_pnl)}>{inr(h.net_pnl, { sign: true })}</strong>
                    <small>{new Date(h.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</small>
                    <small>Sharpe {num(h.sharpe)}</small>
                  </button>
                ))}
              </div>
            </Panel>
          )}
        </div>

        {result ? (
          <WalkResult result={result} capital={meta.risk.capital} />
        ) : (
          <Panel>
            <div className="empty">
              <Route size={28} color="#5b6580" />
              <h3>No walk-forward runs yet</h3>
              <p>Run one to see how a strategy holds up on data it was never tuned on.</p>
            </div>
          </Panel>
        )}
      </div>
    </>
  );
}

function WalkResult({ result, capital }: { result: WalkForwardResult; capital: number }) {
  const m = result.oos_metrics;
  const all = result.windows;
  const t0 = new Date(all[0].train[0]).getTime();
  const t1 = new Date(all[all.length - 1].test[1]).getTime();
  const pct = (d: string) => ((new Date(d).getTime() - t0) / (t1 - t0)) * 100;
  const profitable = all.filter((w) => (w.test_metrics.net_pnl ?? 0) > 0).length;

  return (
    <div>
      <div className="headline">
        <span className={`big ${tone(m.net_pnl)}`}>{inr(m.net_pnl, { sign: true })}</span>
        <span className="muted">
          out of sample, {strategyLabel(result.request.strategy)}. {profitable} of {all.length} test windows made money.
        </span>
      </div>

      <dl className="stats">
        <Stat label="Trades" value={m.trades} />
        <Stat label="Win rate" value={`${num(m.win_rate, 1)}%`} />
        <Stat label="Sharpe" value={num(m.sharpe)} tone={tone(m.sharpe)} />
        <Stat label="Max drawdown" value={`${num(m.max_drawdown_pct, 1)}%`} tone="neg" />
        <Stat label="Profit factor" value={num(m.profit_factor)} />
      </dl>

      <Panel title="Out-of-sample equity">
        <div className="chart">
          <EquityChart data={result.oos_equity} capital={capital} />
        </div>
      </Panel>

      <Panel title="Windows" aside="Train in grey, test in gold" className="trades-panel">
        <div className="windows">
          {all.map((w, i) => (
            <motion.div className="window" key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.04 }}>
              <span className="window-n">{i + 1}</span>
              <div>
                <div className="span-bar">
                  <i style={{ left: `${pct(w.train[0])}%`, width: `${pct(w.train[1]) - pct(w.train[0])}%`, background: "var(--line)" }} />
                  <i style={{ left: `${pct(w.test[0])}%`, width: `${Math.max(1, pct(w.test[1]) - pct(w.test[0]))}%`, background: "var(--marigold)" }} />
                </div>
                <div className="faint" style={{ marginTop: 6 }}>
                  Test {day(w.test[0])} to {day(w.test[1])}:{" "}
                  {Object.entries(w.params).map(([k, v]) => `${paramLabel(k).toLowerCase()} ${v}`).join(", ")}
                </div>
              </div>
              <span className={`num ${tone(w.test_metrics.net_pnl) ?? ""}`} style={{ textAlign: "right" }}>
                {inr(w.test_metrics.net_pnl, { sign: true })}
              </span>
              <span className="faint" style={{ textAlign: "right" }}>
                {w.test_metrics.trades ?? 0} trades
              </span>
            </motion.div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
