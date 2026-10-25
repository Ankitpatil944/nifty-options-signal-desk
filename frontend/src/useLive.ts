import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Candle, LiveEvent, LiveStatus, Price, SignalRow } from "./types";

export interface Notice {
  id: number;
  tone: "info" | "warn";
  text: string;
}

export interface LiveState {
  connected: boolean;
  status: LiveStatus | null;
  prices: Record<string, Price>;
  candles: Record<string, Candle[]>;
  signals: SignalRow[];
  notices: Notice[];
  refreshCandles: () => void;
  freshIds: Set<number>;
}

const MAX_CANDLES = 400;

export function useLive(symbols: string[]): LiveState {
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [prices, setPrices] = useState<Record<string, Price>>({});
  const [candles, setCandles] = useState<Record<string, Candle[]>>({});
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);
  const noticeId = useRef(0);
  // Signals that arrived over the socket this session (they animate in; loaded history doesn't).
  const freshIds = useRef(new Set<number>());

  const notify = useCallback((tone: Notice["tone"], text: string) => {
    const id = ++noticeId.current;
    setNotices((n) => [{ id, tone, text }, ...n].slice(0, 6));
    window.setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), 6000);
  }, []);

  const refreshCandles = useCallback(() => {
    symbols.forEach((s) =>
      api
        .candles(s, 1)
        .then((rows) => setCandles((c) => ({ ...c, [s]: rows })))
        .catch(() => undefined),
    );
  }, [symbols]);

  useEffect(() => {
    if (symbols.length) refreshCandles();
    api.signals(50).then(setSignals).catch(() => undefined);
  }, [symbols, refreshCandles]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: number | undefined;
    let closed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/live`);
      ws.onopen = () => {
        retry = 0;
        setConnected(true);
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) timer = window.setTimeout(connect, Math.min(8000, 500 * 2 ** retry++));
      };
      ws.onmessage = (msg) => {
        const event = JSON.parse(msg.data) as LiveEvent;
        switch (event.type) {
          case "status":
            setStatus(event.data);
            if (Object.keys(event.data.prices).length) setPrices(event.data.prices);
            break;
          case "tick":
            setPrices((p) => ({ ...p, [event.data.symbol]: event.data }));
            break;
          case "candle": {
            const { symbol, ...c } = event.data;
            setCandles((all) => {
              const prev = all[symbol] ?? [];
              const sameDay = prev.length && prev[prev.length - 1].ts.slice(0, 10) === c.ts.slice(0, 10);
              return { ...all, [symbol]: [...(sameDay ? prev : []), c].slice(-MAX_CANDLES) };
            });
            break;
          }
          case "signal":
            freshIds.current.add(event.data.id);
            setSignals((s) => [event.data, ...s]);
            break;
          case "signal_closed":
            setSignals((s) => s.map((row) => (row.id === event.data.id ? event.data : row)));
            break;
          case "skipped":
            notify("info", `${event.data.symbol} ${event.data.side.toLowerCase()} skipped: ${event.data.why}`);
            break;
          case "error":
            notify("warn", event.data.message);
            break;
        }
      };
    };

    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, [notify]);

  return { connected, status, prices, candles, signals, notices, refreshCandles, freshIds: freshIds.current };
}
