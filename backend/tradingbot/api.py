"""FastAPI app serving the dashboard: backtests, walk-forward, journal and a live event stream."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tradingbot.backtest import engine, walkforward
from tradingbot.config import BACKEND_DIR, Settings, get_settings
from tradingbot.data.store import CandleStore, resample
from tradingbot.journal import Journal
from tradingbot.live.runner import LiveRunner
from tradingbot.strategies import REGISTRY

log = logging.getLogger(__name__)


class BacktestBody(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["NIFTY", "BANKNIFTY"])
    strategy: str = "orb"
    params: dict[str, float] = Field(default_factory=dict)
    instrument: Literal["options", "futures"] = "options"
    option_mode: Literal["buy", "sell"] | None = None
    start: str | None = None
    end: str | None = None


class WalkForwardBody(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["NIFTY", "BANKNIFTY"])
    strategy: str = "orb"
    train_days: int = 120
    test_days: int = 40
    objective: Literal["sharpe", "net_pnl", "profit_factor"] = "sharpe"
    instrument: Literal["options", "futures"] = "options"
    option_mode: Literal["buy", "sell"] | None = None


class LiveStartBody(BaseModel):
    source: Literal["kite", "replay"] = "replay"
    speed: float = Field(1.0, gt=0, le=60)
    replay_days: int = Field(1, ge=1, le=20)


class ResultStore:
    def __init__(self, root: Path) -> None:
        self.root = root / "results"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        rid = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        payload = {"id": rid, "kind": kind, "created_at": datetime.now().isoformat(), **payload}
        (self.root / f"{rid}.json").write_text(json.dumps(payload, default=str), encoding="utf-8")
        return payload

    def list(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(self.root.glob("*.json"), reverse=True):
            d = json.loads(path.read_text(encoding="utf-8"))
            m = d.get("metrics") or d.get("oos_metrics") or {}
            out.append({"id": d["id"], "kind": d["kind"], "created_at": d["created_at"],
                        "strategy": d["request"]["strategy"], "symbols": d["request"]["symbols"],
                        "instrument": d["request"].get("instrument"),
                        "option_mode": d["request"].get("option_mode"),
                        "net_pnl": m.get("net_pnl"), "sharpe": m.get("sharpe"), "trades": m.get("trades")})
        return out

    def get(self, rid: str) -> dict[str, Any]:
        path = self.root / f"{Path(rid).name}.json"
        if not path.exists():
            raise HTTPException(404, f"no result {rid}")
        return json.loads(path.read_text(encoding="utf-8"))


def load_frames(settings: Settings, symbols: list[str], start: str | None = None,
                end: str | None = None) -> dict[str, pd.DataFrame]:
    store = CandleStore(settings.data_path, settings.timezone)
    unknown = set(symbols) - set(settings.instruments)
    if unknown:
        raise HTTPException(400, f"unknown symbols {sorted(unknown)}")
    try:
        return {s: resample(store.load(s, 1, start, end), settings.candle_interval) for s in symbols}
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc)) from exc


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    journal = Journal(settings.data_path / "journal.db")
    runner = LiveRunner(settings, journal)
    results = ResultStore(settings.data_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        yield
        await runner.stop()
        await runner.telegram.aclose()

    app = FastAPI(title="Tradingbot", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.runner = runner

    def configured_params(name: str) -> dict[str, float]:
        cfg = settings.strategies.get(name)
        return cfg.params if cfg else {}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        store = CandleStore(settings.data_path, settings.timezone)
        return {
            "symbols": list(settings.instruments),
            "instruments": {k: v.model_dump() for k, v in settings.instruments.items()},
            "strategies": [{"name": c.name, "label": c.label, "description": c.description,
                            "default_params": {**c.default_params, **configured_params(c.name)},
                            "enabled_live": c.name in settings.strategies
                            and settings.strategies[c.name].enabled,
                            "param_grid": c.param_grid} for c in REGISTRY.values()],
            "datasets": store.describe(),
            "session": {k: v.strftime("%H:%M") for k, v in settings.session.model_dump().items()},
            "risk": settings.risk.model_dump(),
            "options": settings.options.model_dump(),
            "kite_configured": bool(settings.secrets.kite_api_key),
            "telegram_configured": bool(settings.secrets.telegram_bot_token and settings.secrets.telegram_chat_id),
        }

    @app.post("/api/backtests")
    async def run_backtest(body: BacktestBody) -> dict[str, Any]:
        if body.strategy not in REGISTRY:
            raise HTTPException(400, f"unknown strategy {body.strategy}")
        frames = load_frames(settings, body.symbols, body.start, body.end)
        req = engine.BacktestRequest(**body.model_dump())

        def work() -> dict[str, Any]:
            return engine.run(settings, REGISTRY[body.strategy](**body.params), frames, req).to_dict()

        try:
            result = await asyncio.to_thread(work)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return results.save("backtest", result)

    @app.post("/api/walkforward")
    async def run_walkforward(body: WalkForwardBody) -> dict[str, Any]:
        if body.strategy not in REGISTRY:
            raise HTTPException(400, f"unknown strategy {body.strategy}")
        frames = load_frames(settings, body.symbols)
        req = walkforward.WalkForwardRequest(**body.model_dump())
        try:
            result = await asyncio.to_thread(walkforward.run, settings, frames, req)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return results.save("walkforward", result)

    @app.get("/api/results")
    def list_results() -> list[dict[str, Any]]:
        return results.list()

    @app.get("/api/results/{rid}")
    def get_result(rid: str) -> dict[str, Any]:
        return results.get(rid)

    @app.get("/api/candles/{symbol}")
    def candles(symbol: str, days: int = 1) -> list[dict[str, Any]]:
        if runner.running and symbol in runner.history:
            df = runner.history[symbol]
        else:
            df = load_frames(settings, [symbol])[symbol]
        cutoff = sorted(set(df.index.normalize()))[-days:][0] if len(df) else None
        df = df[df.index >= cutoff] if cutoff is not None else df
        return [{"ts": ts.isoformat(), **{k: round(float(v), 2) for k, v in row.items()}}
                for ts, row in df[["open", "high", "low", "close"]].iterrows()]

    @app.get("/api/signals")
    def signals(limit: int = 100, source: str | None = None) -> list[dict[str, Any]]:
        return journal.recent(limit, source)

    @app.get("/api/journal/stats")
    def journal_stats(source: str | None = None) -> dict[str, Any]:
        return journal.stats(source)

    @app.get("/api/live/status")
    def live_status() -> dict[str, Any]:
        return runner.status()

    @app.post("/api/live/start")
    async def live_start(body: LiveStartBody) -> dict[str, Any]:
        try:
            await runner.start(body.source, body.speed, body.replay_days)
        except Exception as exc:  # surface login / data problems to the UI as-is
            raise HTTPException(409, str(exc)) from exc
        return runner.status()

    @app.post("/api/live/stop")
    async def live_stop() -> dict[str, Any]:
        await runner.stop()
        return runner.status(running=False)

    @app.post("/api/live/pause")
    async def live_pause(paused: bool = True) -> dict[str, Any]:
        runner.risk.paused = paused
        await runner.publish({"type": "status", "data": runner.status()})
        return runner.status()

    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        runner.subscribers.add(queue)
        try:
            await ws.send_json({"type": "status", "data": runner.status()})
            while True:
                await ws.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            runner.subscribers.discard(queue)

    dist = BACKEND_DIR.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app
