import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { day, inr, num, time } from "../api";
import type { Candle, EquityPoint } from "../types";

const AXIS = { stroke: "#5b6580", fontSize: 12, tickLine: false, axisLine: false } as const;

function TipBox({ title, rows }: { title: string; rows: [string, string, string?][] }) {
  return (
    <div style={{ background: "#1c2336", border: "1px solid #252e45", borderRadius: 10, padding: "8px 12px", fontSize: 13 }}>
      <div style={{ color: "#8a94ab", marginBottom: 4 }}>{title}</div>
      {rows.map(([k, v, color]) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
          <span style={{ color: "#8a94ab" }}>{k}</span>
          <strong style={{ color: color ?? "#e6eaf2" }}>{v}</strong>
        </div>
      ))}
    </div>
  );
}

/** Intraday close line for an index tile. Colour follows the day's direction. */
export function Spark({ candles, up }: { candles: Candle[]; up: boolean }) {
  const color = up ? "#38d3ae" : "#ff6b7d";
  const id = up ? "spark-up" : "spark-down";
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={candles} margin={{ top: 6, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Tooltip
          cursor={{ stroke: "#5b6580", strokeDasharray: "3 3" }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TipBox title={time((payload[0].payload as Candle).ts)} rows={[["Close", num((payload[0].payload as Candle).close, 1)]]} />
            ) : null
          }
        />
        <Area type="monotone" dataKey="close" stroke={color} strokeWidth={1.75} fill={`url(#${id})`} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function EquityChart({ data, capital }: { data: EquityPoint[]; capital: number }) {
  const last = data.length ? data[data.length - 1].equity : capital;
  const color = last >= capital ? "#38d3ae" : "#ff6b7d";
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.25} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#1e263a" vertical={false} />
        <XAxis dataKey="date" {...AXIS} tickFormatter={day} minTickGap={48} />
        <YAxis {...AXIS} width={72} domain={["auto", "auto"]} tickFormatter={(v) => `₹${(v / 100000).toFixed(1)}L`} />
        <ReferenceLine y={capital} stroke="#5b6580" strokeDasharray="4 4" />
        <Tooltip
          cursor={{ stroke: "#5b6580", strokeDasharray: "3 3" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as EquityPoint;
            return <TipBox title={day(p.date)} rows={[["Equity", inr(p.equity)], ["P&L", inr(p.equity - capital, { sign: true }), p.equity >= capital ? "#38d3ae" : "#ff6b7d"]]} />;
          }}
        />
        <Area type="monotone" dataKey="equity" stroke={color} strokeWidth={2} fill="url(#eq)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function DrawdownChart({ data }: { data: EquityPoint[] }) {
  let peak = -Infinity;
  const dd = data.map((p) => {
    peak = Math.max(peak, p.equity);
    return { date: p.date, dd: ((p.equity - peak) / peak) * 100 };
  });
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={dd} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1e263a" vertical={false} />
        <XAxis dataKey="date" {...AXIS} tickFormatter={day} minTickGap={48} />
        <YAxis {...AXIS} width={48} tickFormatter={(v) => `${v.toFixed(0)}%`} />
        <Tooltip
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TipBox title={day(String(payload[0].payload.date))} rows={[["Drawdown", `${Number(payload[0].value).toFixed(2)}%`, "#ff6b7d"]]} />
            ) : null
          }
        />
        <Line type="monotone" dataKey="dd" stroke="#ff6b7d" strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
