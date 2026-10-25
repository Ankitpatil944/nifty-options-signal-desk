export type Side = "LONG" | "SHORT";

export interface StrategyMeta {
  name: string;
  label: string;
  description: string;
  default_params: Record<string, number>;
  param_grid: Record<string, number[]>;
  enabled_live: boolean;
}

export interface Dataset {
  symbol: string;
  interval: number;
  rows: number;
  start: string | null;
  end: string | null;
}

export interface Meta {
  symbols: string[];
  strategies: StrategyMeta[];
  datasets: Dataset[];
  session: Record<string, string>;
  risk: Record<string, number>;
  options: { mode: "buy" | "sell" } & Record<string, unknown>;
  kite_configured: boolean;
  telegram_configured: boolean;
}

export interface Price {
  symbol: string;
  ts: string;
  price: number;
  change_pct: number | null;
}

export interface RiskSnapshot {
  day: string | null;
  realised_today: number;
  daily_loss_limit: number;
  trades_today: number;
  max_trades_per_day: number;
  open_positions: number;
  paused: boolean;
  risk_per_trade: number;
  equity: number;
}

export interface LiveStatus {
  running: boolean;
  source: "kite" | "replay" | null;
  started_at: string | null;
  symbols: string[];
  strategies: string[];
  prices: Record<string, Price>;
  risk: RiskSnapshot;
  open_signals: number;
  telegram: boolean;
  option_mode: "buy" | "sell";
}

export interface OptionLeg {
  action: "BUY" | "SELL";
  right: "CE" | "PE";
  strike: number;
  expiry: string;
  premium: number;
  priced_by: "market" | "model";
}

export interface SignalRow {
  id: number;
  created_at: string;
  source: string;
  symbol: string;
  strategy: string;
  side: Side;
  entry: number;
  stop: number;
  target: number;
  reason: string;
  confidence: number;
  contract: string;
  structure: string;
  lots: number;
  qty: number;
  entry_value: number;
  value_at_stop: number;
  value_at_target: number;
  option: { legs: OptionLeg[]; max_loss_per_unit: number; iv: number } | null;
  status: "OPEN" | "TARGET" | "STOP" | "TIME" | "UNTRACKED";
  exit_at: string | null;
  exit_spot: number | null;
  exit_value: number | null;
  pnl: number | null;
}

export interface Candle {
  symbol?: string;
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface Trade {
  symbol: string;
  side: Side;
  signal_ts: string;
  entry_ts: string;
  exit_ts: string;
  entry_spot: number;
  exit_spot: number;
  stop: number;
  target: number;
  exit_reason: string;
  structure: string;
  contract: string;
  lots: number;
  qty: number;
  gross_pnl: number;
  costs: number;
  net_pnl: number;
  r_multiple: number | null;
  reason: string;
}

export interface Metrics {
  trades: number;
  net_pnl: number;
  gross_pnl?: number;
  costs?: number;
  return_pct: number;
  cagr_pct?: number | null;
  win_rate?: number;
  avg_win?: number;
  avg_loss?: number;
  profit_factor?: number | null;
  expectancy?: number;
  avg_r?: number | null;
  sharpe?: number | null;
  sortino?: number | null;
  max_drawdown?: number;
  max_drawdown_pct?: number;
  avg_hold_minutes?: number;
  max_consecutive_losses?: number;
  cost_drag_pct?: number;
  exit_reasons?: Record<string, number>;
  by_side?: Record<string, { count: number; sum: number }>;
  by_symbol?: Record<string, { count: number; sum: number }>;
  note?: string;
}

export interface EquityPoint {
  date: string;
  equity: number;
}

export interface BacktestRequest {
  symbols: string[];
  strategy: string;
  params: Record<string, number>;
  instrument: "options" | "futures";
  option_mode: "buy" | "sell" | null;
  start: string | null;
  end: string | null;
}

export interface BacktestResult {
  id: string;
  kind: "backtest";
  created_at: string;
  request: BacktestRequest;
  metrics: Metrics;
  skipped: Record<string, number>;
  equity: EquityPoint[];
  trades: Trade[];
}

export interface WalkWindow {
  train: [string, string];
  test: [string, string];
  params: Record<string, number>;
  train_score: number | null;
  train_metrics: Partial<Metrics>;
  test_metrics: Partial<Metrics>;
}

export interface WalkForwardResult {
  id: string;
  kind: "walkforward";
  created_at: string;
  request: { strategy: string; symbols: string[]; train_days: number; test_days: number; objective: string };
  windows: WalkWindow[];
  oos_metrics: Metrics;
  oos_equity: EquityPoint[];
  grid_size: number;
}

export interface ResultSummary {
  id: string;
  kind: "backtest" | "walkforward";
  created_at: string;
  strategy: string;
  symbols: string[];
  instrument: string | null;
  option_mode: string | null;
  net_pnl: number | null;
  sharpe: number | null;
  trades: number | null;
}

export interface JournalStats {
  closed: number;
  net_pnl: number;
  win_rate: number;
  expectancy: number;
  by_strategy: { strategy: string; n: number; pnl: number; win_rate: number }[];
}

export type LiveEvent =
  | { type: "status"; data: LiveStatus }
  | { type: "tick"; data: Price }
  | { type: "candle"; data: Candle & { symbol: string } }
  | { type: "signal"; data: SignalRow }
  | { type: "signal_closed"; data: SignalRow }
  | { type: "skipped"; data: { symbol: string; side: Side; strategy: string; why: string } }
  | { type: "error"; data: { message: string } };
