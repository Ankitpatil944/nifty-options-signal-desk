import { BookOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { api, day, inr, num, strategyLabel, time } from "../api";
import { Panel, tone } from "../components/ui";
import type { BacktestResult, JournalStats, ResultSummary, SignalRow } from "../types";

const STATUS: Record<SignalRow["status"], string> = {
  OPEN: "Open",
  TARGET: "Target",
  STOP: "Stop",
  TIME: "Square-off",
  UNTRACKED: "Not tracked",
};

/**
 * Live (or replayed) suggestions next to what the backtest expected for the same strategy.
 * A big gap between the two columns is the first sign of overfitting or a modelling error.
 */
export function Journal({ refreshKey }: { refreshKey: number }) {
  const [rows, setRows] = useState<SignalRow[]>([]);
  const [stats, setStats] = useState<JournalStats | null>(null);
  const [baselines, setBaselines] = useState<Record<string, BacktestResult["metrics"]>>({});

  useEffect(() => {
    api.signals(300).then(setRows).catch(() => undefined);
    api.journalStats().then(setStats).catch(() => undefined);
  }, [refreshKey]);

  useEffect(() => {
    api
      .results()
      .then(async (all: ResultSummary[]) => {
        const latest: Record<string, string> = {};
        for (const r of all) if (r.kind === "backtest" && !latest[r.strategy]) latest[r.strategy] = r.id;
        const entries = await Promise.all(
          Object.entries(latest).map(async ([s, id]) => [s, (await api.result<BacktestResult>(id)).metrics] as const),
        );
        setBaselines(Object.fromEntries(entries));
      })
      .catch(() => undefined);
  }, []);

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Journal</h1>
          <p>
            Every suggestion the bot has made and how it played out, scored with the same exit rules as the backtester.
            Compare the two to see whether live results match the expectation.
          </p>
        </div>
      </header>

      {stats && stats.closed > 0 && (
        <div className="compare">
          {stats.by_strategy.map((s) => {
            const b = baselines[s.strategy];
            return (
              <Panel key={s.strategy} title={strategyLabel(s.strategy)} aside={`${s.n} closed`}>
                <dl className="kv">
                  <div>
                    <dt className="muted">Win rate, live against backtest</dt>
                    <dd className="vs">
                      <strong>{num(s.win_rate * 100, 0)}%</strong>
                      <span className="muted">vs {b ? `${num(b.win_rate, 0)}%` : "no backtest yet"}</span>
                    </dd>
                  </div>
                  <div className="kv-row">
                    <dt>Live P&L per suggestion</dt>
                    <dd className={tone(s.pnl)}>{inr(s.pnl / s.n, { sign: true })}</dd>
                  </div>
                  <div className="kv-row">
                    <dt>Backtest expectancy</dt>
                    <dd className={tone(b?.expectancy)}>{b ? inr(b.expectancy, { sign: true }) : "–"}</dd>
                  </div>
                </dl>
              </Panel>
            );
          })}
        </div>
      )}

      <Panel title="Suggestions" aside={stats ? `${stats.closed} closed, net ${inr(stats.net_pnl, { sign: true })}` : undefined}>
        {rows.length === 0 ? (
          <div className="empty">
            <BookOpen size={28} color="#5b6580" />
            <h3>The journal is empty</h3>
            <p>Start the bot from the live desk. Each suggestion is logged here with its outcome.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Index</th>
                  <th>Strategy</th>
                  <th>Contract</th>
                  <th className="num">Entry</th>
                  <th className="num">SL / Target</th>
                  <th className="num">Lots</th>
                  <th>Outcome</th>
                  <th className="num">Est. P&L</th>
                  <th>Feed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>{day(r.created_at)}, {time(r.created_at)}</td>
                    <td><span className={`tag ${r.side === "LONG" ? "long" : "short"}`}>{r.symbol}</span></td>
                    <td className="muted">{strategyLabel(r.strategy)}</td>
                    <td>{r.contract}</td>
                    <td className="num">{num(r.entry, 1)}</td>
                    <td className="num muted">{num(r.stop, 0)} / {num(r.target, 0)}</td>
                    <td className="num">{r.lots}</td>
                    <td className={r.status === "TARGET" ? "pos" : r.status === "STOP" ? "neg" : "muted"}>{STATUS[r.status]}</td>
                    <td className={`num ${tone(r.pnl) ?? ""}`}>{r.status === "OPEN" ? "–" : inr(r.pnl, { sign: true })}</td>
                    <td className="faint">{r.source === "kite" ? "Kite" : "Replay"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
