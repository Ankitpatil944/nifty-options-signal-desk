import { AnimatePresence, motion } from "framer-motion";
import { Pause, Play, Radio, Square } from "lucide-react";
import { useMemo, useState } from "react";
import { api, inr, num } from "../api";
import { Spark } from "../components/Charts";
import { Ticket } from "../components/Ticket";
import { Panel, Segmented } from "../components/ui";
import type { Meta } from "../types";
import type { LiveState } from "../useLive";

export function LiveDesk({ meta, live }: { meta: Meta; live: LiveState }) {
  const [source, setSource] = useState<"replay" | "kite">(meta.kite_configured ? "kite" : "replay");
  const [speed, setSpeed] = useState("0.5");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { status, prices, candles, signals, freshIds } = live;
  const running = status?.running ?? false;
  const isFresh = (id: number) => freshIds.has(id);

  const today = useMemo(() => {
    const open = signals.filter((s) => s.status === "OPEN");
    const closed = signals.filter((s) => s.status !== "OPEN").slice(0, 12);
    return { open, closed };
  }, [signals]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const start = () =>
    act(async () => {
      await api.start(source, Number(speed), 1);
      live.refreshCandles();
    });

  const risk = status?.risk;
  const lossUsed = risk ? Math.min(100, (Math.max(0, -risk.realised_today) / risk.daily_loss_limit) * 100) : 0;
  const tradesUsed = risk ? (risk.trades_today / risk.max_trades_per_day) * 100 : 0;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Live desk</h1>
          <p>
            {running
              ? `Watching ${status?.symbols.join(" and ")} on ${status?.source === "kite" ? "the Kite feed" : "replayed history"}. Suggestions go to Telegram as they appear.`
              : "Start the bot to stream index prices and get option suggestions between 09:20 and 12:00."}
          </p>
        </div>
        <div className="controls">
          {!running && (
            <>
              <Segmented
                label="Data source"
                value={source}
                onChange={setSource}
                options={[
                  { value: "kite", label: "Kite live" },
                  { value: "replay", label: "Replay" },
                ]}
              />
              {source === "replay" && (
                <select className="select" value={speed} onChange={(e) => setSpeed(e.target.value)} aria-label="Replay speed">
                  <option value="2">Slow replay</option>
                  <option value="0.5">Fast replay</option>
                  <option value="0.05">Very fast replay</option>
                </select>
              )}
              <button className="btn primary" onClick={start} disabled={busy}>
                <Play size={16} /> Start bot
              </button>
            </>
          )}
          {running && (
            <>
              <button className="btn" onClick={() => act(() => api.pause(!risk?.paused))} disabled={busy}>
                {risk?.paused ? <Play size={16} /> : <Pause size={16} />}
                {risk?.paused ? "Resume suggestions" : "Pause suggestions"}
              </button>
              <button className="btn danger" onClick={() => act(api.stop)} disabled={busy}>
                <Square size={14} /> Stop bot
              </button>
            </>
          )}
        </div>
      </header>

      {error && (
        <div className="error-box" style={{ marginBottom: 20 }}>
          {error}
        </div>
      )}
      {source === "kite" && !meta.kite_configured && !running && (
        <div className="error-box" style={{ marginBottom: 20 }}>
          Kite isn't set up yet. Add KITE_API_KEY and KITE_API_SECRET to backend/.env, then run <code>tradingbot login</code>.
        </div>
      )}

      <div className="indices">
        {meta.symbols.map((sym) => {
          const p = prices[sym];
          const series = candles[sym] ?? [];
          const last = p?.price ?? series[series.length - 1]?.close;
          const up = (p?.change_pct ?? 0) >= 0;
          return (
            <Panel key={sym} className="index-tile">
              <div className="index-top">
                <span className="index-name">{sym === "NIFTY" ? "Nifty 50" : "Nifty Bank"}</span>
                {p?.change_pct !== null && p?.change_pct !== undefined && (
                  <span className={up ? "pos" : "neg"}>
                    {up ? "+" : ""}
                    {num(p.change_pct)}%
                  </span>
                )}
              </div>
              <div className="index-price">{last ? num(last, 2) : "–"}</div>
              <div className="index-chart">{series.length > 1 && <Spark candles={series} up={up} />}</div>
            </Panel>
          );
        })}
      </div>

      <div className="desk">
        <div className="feed">
          <div className="feed-head">
            <h2>Suggestions</h2>
            <span className="muted">
              {today.open.length} open, {today.closed.length} recent closed
            </span>
          </div>

          {signals.length === 0 && (
            <Panel>
              <div className="empty">
                <Radio size={28} color="#5b6580" />
                <h3>No suggestions yet</h3>
                <p>When a strategy's conditions line up inside the entry window, a ticket appears here and on Telegram.</p>
              </div>
            </Panel>
          )}

          <AnimatePresence initial={false}>
            {[...today.open, ...today.closed].map((row) => (
              <Ticket key={row.id} row={row} livePrice={prices[row.symbol]?.price} fresh={isFresh(row.id)} />
            ))}
          </AnimatePresence>
        </div>

        <aside className="side-panel">
          <Panel title="Session" aside={running ? (risk?.paused ? "Paused" : "Running") : "Stopped"}>
            <dl className="kv">
              <div className="kv-row">
                <dt>Realised today</dt>
                <dd className={risk && risk.realised_today < 0 ? "neg" : risk && risk.realised_today > 0 ? "pos" : ""}>
                  {inr(risk?.realised_today ?? 0, { sign: true })}
                </dd>
              </div>
              <div>
                <div className="kv-row">
                  <dt>Daily loss limit</dt>
                  <dd>{inr(risk?.daily_loss_limit)}</dd>
                </div>
                <div className="meter">
                  <motion.div animate={{ width: `${lossUsed}%` }} style={{ background: lossUsed > 75 ? "var(--short)" : "var(--marigold)" }} />
                </div>
              </div>
              <div>
                <div className="kv-row">
                  <dt>Suggestions today</dt>
                  <dd>
                    {risk?.trades_today ?? 0} of {risk?.max_trades_per_day ?? meta.risk.max_trades_per_day}
                  </dd>
                </div>
                <div className="meter">
                  <motion.div animate={{ width: `${tradesUsed}%` }} style={{ background: "var(--muted)" }} />
                </div>
              </div>
              <div className="kv-row">
                <dt>Risk per trade</dt>
                <dd>{inr(risk?.risk_per_trade ?? (meta.risk.capital * meta.risk.risk_per_trade_pct) / 100)}</dd>
              </div>
              <div className="kv-row">
                <dt>Equity</dt>
                <dd>{inr(risk?.equity ?? meta.risk.capital)}</dd>
              </div>
            </dl>
          </Panel>

          <Panel title="Setup">
            <dl className="kv">
              <div className="kv-row">
                <dt>Option style</dt>
                <dd>{meta.options.mode === "buy" ? "Buy CE / PE" : "Credit spreads"}</dd>
              </div>
              <div className="kv-row">
                <dt>Entry window</dt>
                <dd>
                  {meta.session.entry_start} to {meta.session.entry_end}
                </dd>
              </div>
              <div className="kv-row">
                <dt>Strategies</dt>
                <dd>{meta.strategies.filter((s) => s.enabled_live).length} active</dd>
              </div>
              <div className="kv-row">
                <dt>Telegram</dt>
                <dd className={meta.telegram_configured ? "pos" : "faint"}>{meta.telegram_configured ? "Connected" : "Not set up"}</dd>
              </div>
            </dl>
          </Panel>
        </aside>
      </div>
    </>
  );
}
