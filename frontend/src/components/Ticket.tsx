import { motion } from "framer-motion";
import { day, inr, num, strategyLabel, time } from "../api";
import type { SignalRow } from "../types";

const clamp = (x: number) => Math.max(0, Math.min(100, x));

/** Maps an index level onto the stop-to-target ladder (0% = stop, 100% = target) for either side. */
function ladderPct(row: SignalRow, price: number): number {
  return clamp(((price - row.stop) / (row.target - row.stop)) * 100);
}

const STATUS_LABEL: Record<SignalRow["status"], string> = {
  OPEN: "Open",
  TARGET: "Target hit",
  STOP: "Stopped out",
  TIME: "Closed at square-off",
  UNTRACKED: "Not tracked",
};

export function Ticket({ row, livePrice, fresh }: { row: SignalRow; livePrice?: number; fresh?: boolean }) {
  const side = row.side === "LONG" ? "long" : "short";
  const isSpread = row.structure.endsWith("spread");
  const open = row.status === "OPEN";
  const now = open ? livePrice : row.exit_spot ?? undefined;
  const entryPct = ladderPct(row, row.entry);
  const modelPriced = row.option?.legs?.[0]?.priced_by === "model";

  const premiums = isSpread
    ? [
        ["Credit", inr(-row.entry_value, { fine: true })],
        ["Exit at stop", inr(-row.value_at_stop, { fine: true })],
        ["Exit at target", inr(-row.value_at_target, { fine: true })],
        ["Max loss / unit", inr(row.option?.max_loss_per_unit, { fine: true })],
      ]
    : [
        ["Buy at", inr(row.entry_value, { fine: true })],
        ["Stop", inr(row.value_at_stop, { fine: true })],
        ["Target", inr(row.value_at_target, { fine: true })],
        ["Size", `${row.lots} lot${row.lots === 1 ? "" : "s"} (${row.qty} qty)`],
      ];

  return (
    <motion.article
      layout
      className={`ticket ${side} ${open ? "" : "closed"}`}
      initial={fresh ? { opacity: 0, y: -18, scale: 0.97 } : false}
      animate={{
        opacity: open ? 1 : 0.72,
        y: 0,
        scale: 1,
        boxShadow: fresh
          ? ["0 0 0 0 rgba(240,176,63,0)", "0 0 0 6px rgba(240,176,63,0.28)", "0 0 0 0 rgba(240,176,63,0)"]
          : "0 0 0 0 rgba(240,176,63,0)",
      }}
      transition={{ type: "spring", stiffness: 380, damping: 30, boxShadow: { duration: 1.6 } }}
    >
      <div className="ticket-head">
        <div>
          <div className="ticket-meta">
            <span className={`tag ${side}`}>
              {row.symbol} {row.side === "LONG" ? "long" : "short"}
            </span>
            <span>{strategyLabel(row.strategy)}</span>
            <span className="faint">
              {day(row.created_at)}, {time(row.created_at)}
            </span>
          </div>
          <div className="contract">{row.contract}</div>
          <p className="ticket-reason">{row.reason}</p>
        </div>
        <span className="tag gold" title="How strongly the setup matched the strategy's rules">
          {Math.round(row.confidence * 100)}% fit
        </span>
      </div>

      <dl className="premiums">
        {premiums.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>

      <div className="ladder" style={{ ["--entry" as string]: `${entryPct}%` }} aria-label="Index price between stop and target">
        <div className="ladder-track" />
        <div className="ladder-mark" style={{ left: `${entryPct}%` }} />
        {now !== undefined && (
          <motion.div
            className="ladder-now"
            initial={false}
            animate={{ left: `${ladderPct(row, now)}%` }}
            transition={{ type: "spring", stiffness: 140, damping: 20 }}
            title={`Index ${num(now, 1)}`}
          />
        )}
        <div className="ladder-labels">
          <span>SL {num(row.stop, 0)}</span>
          <span className="mid" style={{ left: `${entryPct}%` }}>
            Entry {num(row.entry, 0)}
          </span>
          <span>Target {num(row.target, 0)}</span>
        </div>
      </div>

      {(!open || modelPriced) && (
        <div className="outcome">
          {open ? (
            <span className="faint">Premiums are model estimates. Check the live quote before ordering.</span>
          ) : (
            <>
              <span className="muted">{STATUS_LABEL[row.status]}</span>
              <strong className={row.pnl && row.pnl > 0 ? "pos" : "neg"}>{inr(row.pnl, { sign: true })}</strong>
            </>
          )}
        </div>
      )}
    </motion.article>
  );
}
