"""Typed configuration loaded from config/settings.yaml plus secrets from .env / environment."""

from __future__ import annotations

import os
from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = BACKEND_DIR / "config" / "settings.yaml"


def _parse_time(value: Any) -> time:
    if isinstance(value, time):
        return value
    hh, mm = str(value).split(":")
    return time(int(hh), int(mm))


class SessionConfig(BaseModel):
    market_open: time
    market_close: time
    entry_start: time
    entry_end: time
    square_off: time

    @field_validator("*", mode="before")
    @classmethod
    def _parse(cls, value: Any) -> time:
        return _parse_time(value)


class InstrumentConfig(BaseModel):
    kite_token: int
    kite_symbol: str
    option_prefix: str
    lot_size: int
    strike_step: int
    expiry: Literal["weekly", "monthly"]
    expiry_weekday: int = Field(ge=0, le=6)
    iv: float
    slippage_points: float


class OptionCostConfig(BaseModel):
    stt_sell: float
    exchange_txn: float
    stamp_buy: float
    slippage_per_unit: float


class FuturesCostConfig(BaseModel):
    stt_sell: float
    exchange_txn: float
    stamp_buy: float


class CostConfig(BaseModel):
    brokerage_per_order: float
    options: OptionCostConfig
    futures: FuturesCostConfig
    sebi_fee: float
    gst: float


class RiskConfig(BaseModel):
    capital: float
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_trades_per_day: int
    max_open_positions: int
    max_lots: int


class OptionsConfig(BaseModel):
    mode: Literal["buy", "sell"]
    buy_moneyness: int
    sell_short_offset: int
    spread_width: int
    min_days_to_expiry: float


class StrategyConfig(BaseModel):
    enabled: bool = True
    params: dict[str, float] = Field(default_factory=dict)


class TelegramConfig(BaseModel):
    enabled: bool = True


class ApiConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class Secrets(BaseModel):
    kite_api_key: str | None = None
    kite_api_secret: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class Settings(BaseModel):
    timezone: str
    data_dir: Path
    session: SessionConfig
    instruments: dict[str, InstrumentConfig]
    candle_interval: int
    costs: CostConfig
    risk: RiskConfig
    options: OptionsConfig
    strategies: dict[str, StrategyConfig]
    telegram: TelegramConfig
    api: ApiConfig
    secrets: Secrets = Field(default_factory=Secrets)

    @property
    def data_path(self) -> Path:
        path = self.data_dir if self.data_dir.is_absolute() else BACKEND_DIR / self.data_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader so we don't need another dependency. Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_settings(path: Path | None = None) -> Settings:
    _load_dotenv(BACKEND_DIR / ".env")
    raw = yaml.safe_load((path or DEFAULT_CONFIG).read_text(encoding="utf-8"))
    raw["secrets"] = {
        "kite_api_key": os.getenv("KITE_API_KEY") or None,
        "kite_api_secret": os.getenv("KITE_API_SECRET") or None,
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN") or None,
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID") or None,
    }
    return Settings.model_validate(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
