import type {
  BacktestRequest,
  BacktestResult,
  Candle,
  JournalStats,
  LiveStatus,
  Meta,
  ResultSummary,
  SignalRow,
  WalkForwardResult,
} from "./types";

export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("Can't reach the backend. Start it with `tradingbot serve`.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ? String(body.detail) : `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  meta: () => call<Meta>("/api/meta"),
  status: () => call<LiveStatus>("/api/live/status"),
  start: (source: "kite" | "replay", speed: number, replay_days: number) =>
    post<LiveStatus>("/api/live/start", { source, speed, replay_days }),
  stop: () => post<LiveStatus>("/api/live/stop"),
  pause: (paused: boolean) => post<LiveStatus>(`/api/live/pause?paused=${paused}`),
  candles: (symbol: string, days = 1) => call<Candle[]>(`/api/candles/${symbol}?days=${days}`),
  signals: (limit = 200) => call<SignalRow[]>(`/api/signals?limit=${limit}`),
  journalStats: () => call<JournalStats>("/api/journal/stats"),
  backtest: (req: Omit<BacktestRequest, "start" | "end"> & { start?: string; end?: string }) =>
    post<BacktestResult>("/api/backtests", req),
  walkforward: (req: {
    symbols: string[];
    strategy: string;
    train_days: number;
    test_days: number;
    objective: string;
    instrument: string;
    option_mode: string | null;
  }) => post<WalkForwardResult>("/api/walkforward", req),
  results: () => call<ResultSummary[]>("/api/results"),
  result: <T = BacktestResult | WalkForwardResult>(id: string) => call<T>(`/api/results/${id}`),
};

const inrFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inrFine = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function inr(value: number | null | undefined, opts: { sign?: boolean; fine?: boolean } = {}): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const fmt = opts.fine || Math.abs(value) < 100 ? inrFine : inrFmt;
  const sign = opts.sign && value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}₹${fmt.format(Math.abs(value))}`;
}

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function strategyLabel(name: string): string {
  return { orb: "Opening range breakout", ema_trend: "EMA trend", vwap_reversion: "VWAP reversion" }[name] ?? name;
}
