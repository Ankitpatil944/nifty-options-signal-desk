"""Command line entry point: `tradingbot --help`."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, timedelta
from typing import Annotated

import typer

from tradingbot.config import get_settings
from tradingbot.data.store import CandleStore, resample

app = typer.Typer(add_completion=False, no_args_is_help=True, help="NIFTY / BANKNIFTY options signal engine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SymbolsOpt = Annotated[list[str] | None, typer.Option("--symbol", "-s", help="Repeatable. Default: all")]


def _symbols(symbols: list[str] | None) -> list[str]:
    return symbols or list(get_settings().instruments)


@app.command()
def synth(days: int = 500, symbols: SymbolsOpt = None, seed: int = 7) -> None:
    """Generate synthetic 1-minute history so everything runs without a Kite subscription."""
    from tradingbot.data import synthetic

    settings = get_settings()
    store = CandleStore(settings.data_path, settings.timezone)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=int(days * 1.45))
    seeds = {"NIFTY": (24500.0, 0.14), "BANKNIFTY": (52000.0, 0.17)}
    for sym in _symbols(symbols):
        px, vol = seeds.get(sym, (20000.0, 0.15))
        df = synthetic.generate(sym, start.isoformat(), end.isoformat(), px, vol, seed)
        typer.echo(f"{sym}: {len(df):,} synthetic bars -> {store.save(sym, 1, df)}")


@app.command()
def login() -> None:
    """Daily Kite login: opens the login URL, then exchanges the request_token for an access token."""
    import webbrowser

    from tradingbot.data import kite

    settings = get_settings()
    url = kite.login_url(settings)
    typer.echo(f"Log in here (opening browser):\n  {url}")
    webbrowser.open(url)
    token = typer.prompt("Paste the request_token from the redirect URL")
    kite.complete_login(settings, token.strip())
    typer.echo("Kite session saved for today.")


@app.command()
def download(days: int = 365, symbols: SymbolsOpt = None) -> None:
    """Download 1-minute index history from Kite (chunked + throttled) into the local store."""
    from tradingbot.data import kite

    settings = get_settings()
    store = CandleStore(settings.data_path, settings.timezone)
    end = date.today()
    for sym in _symbols(symbols):
        df = kite.download_history(settings, sym, end - timedelta(days=days), end, 1)
        typer.echo(f"{sym}: {len(df):,} bars -> {store.save(sym, 1, df)}")


@app.command()
def backtest(
    strategy: str = "orb",
    symbols: SymbolsOpt = None,
    instrument: str = "options",
    mode: Annotated[str | None, typer.Option(help="buy | sell (options only)")] = None,
    start: str | None = None,
    end: str | None = None,
    params: Annotated[str, typer.Option(help='JSON, e.g. \'{"rr": 2.5}\'')] = "{}",
) -> None:
    """Run one backtest and print the summary."""
    from tradingbot.api import ResultStore
    from tradingbot.backtest import engine
    from tradingbot.strategies import build

    settings = get_settings()
    syms = _symbols(symbols)
    store = CandleStore(settings.data_path, settings.timezone)
    frames = {s: resample(store.load(s, 1, start, end), settings.candle_interval) for s in syms}
    p = json.loads(params)
    req = engine.BacktestRequest(syms, strategy, p, instrument, mode, start, end)  # type: ignore[arg-type]
    result = engine.run(settings, build(strategy, **p), frames, req)
    saved = ResultStore(settings.data_path).save("backtest", result.to_dict())
    typer.echo(json.dumps({k: v for k, v in result.metrics.items() if not isinstance(v, dict)}, indent=2))
    typer.echo(f"skipped: {result.skipped}\nsaved as {saved['id']}")


@app.command(name="walkforward")
def walkforward_cmd(strategy: str = "orb", symbols: SymbolsOpt = None, train_days: int = 120,
                    test_days: int = 40, instrument: str = "options", mode: str | None = None) -> None:
    """Rolling optimise-then-test validation; prints the out-of-sample summary."""
    from tradingbot.api import ResultStore
    from tradingbot.backtest import walkforward

    settings = get_settings()
    syms = _symbols(symbols)
    store = CandleStore(settings.data_path, settings.timezone)
    frames = {s: resample(store.load(s, 1), settings.candle_interval) for s in syms}
    req = walkforward.WalkForwardRequest(syms, strategy, train_days, test_days, instrument=instrument,  # type: ignore[arg-type]
                                         option_mode=mode)
    result = walkforward.run(settings, frames, req)
    saved = ResultStore(settings.data_path).save("walkforward", result)
    for w in result["windows"]:
        typer.echo(f"{w['test'][0]}..{w['test'][1]}  {w['params']}  oos pnl {w['test_metrics']['net_pnl']}")
    oos = {k: v for k, v in result["oos_metrics"].items() if not isinstance(v, dict)}
    typer.echo(json.dumps(oos, indent=2) + f"\nsaved as {saved['id']}")


@app.command()
def live(source: str = "replay", speed: float = 1.0, replay_days: int = 1) -> None:
    """Run the signal bot without the dashboard. Ctrl+C to stop."""
    from tradingbot.journal import Journal
    from tradingbot.live.runner import LiveRunner

    settings = get_settings()

    async def main() -> None:
        runner = LiveRunner(settings, Journal(settings.data_path / "journal.db"))
        await runner.start(source, speed, replay_days)  # type: ignore[arg-type]
        try:
            while runner.running:
                await asyncio.sleep(1)
        finally:
            await runner.stop()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        typer.echo("stopped")


@app.command()
def serve(host: str | None = None, port: int | None = None) -> None:
    """Start the API (and the built dashboard, if frontend/dist exists)."""
    import uvicorn

    from tradingbot.api import create_app

    settings = get_settings()
    uvicorn.run(create_app(settings), host=host or settings.api.host, port=port or settings.api.port)


if __name__ == "__main__":
    app()
