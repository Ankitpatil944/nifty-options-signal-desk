"""Telegram delivery and a few chat commands, via the plain Bot HTTP API (no extra library)."""

from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)

CommandHandler = Callable[[str], Awaitable[str]]


class Telegram:
    def __init__(self, token: str | None, chat_id: str | None, enabled: bool = True) -> None:
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled and bool(token and chat_id)
        self._client = httpx.AsyncClient(timeout=35)

    @property
    def base(self) -> str:
        return f"https://api.telegram.org/bot{self.token}"

    async def send(self, text: str) -> bool:
        if not self.enabled:
            log.info("telegram disabled; message:\n%s", text)
            return False
        try:
            r = await self._client.post(f"{self.base}/sendMessage", json={
                "chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                "disable_web_page_preview": True})
            r.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.warning("telegram send failed: %s", exc)
            return False

    async def poll_commands(self, handler: CommandHandler) -> None:
        """Long-poll for /commands from the configured chat only."""
        if not self.enabled:
            return
        offset = 0
        while True:
            try:
                r = await self._client.get(f"{self.base}/getUpdates", params={"timeout": 30, "offset": offset})
                r.raise_for_status()
                for update in r.json().get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message") or {}
                    if str(msg.get("chat", {}).get("id")) != str(self.chat_id):
                        continue
                    text = (msg.get("text") or "").strip()
                    if text.startswith("/"):
                        await self.send(await handler(text.split()[0].split("@")[0].lower()))
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("telegram poll failed: %s", exc)
                await asyncio.sleep(5)

    async def aclose(self) -> None:
        await self._client.aclose()


def _inr(x: float) -> str:
    return f"₹{x:,.0f}" if abs(x) >= 100 else f"₹{x:,.2f}"


def format_signal(s: dict[str, Any]) -> str:
    arrow = "🟢" if s["side"] == "LONG" else "🔴"
    lines = [
        f"{arrow} <b>{s['symbol']} {s['side']}</b>  ·  {html.escape(s['strategy_label'])}",
        "",
        f"<b>{html.escape(s['contract'])}</b>",
    ]
    if s.get("structure", "").endswith("spread"):
        lines.append(f"Net credit ≈ {_inr(-s['entry_value'])} per unit · max loss {_inr(s['max_loss'])} per unit")
        lines.append(f"Exit if spread value reaches ≈ {_inr(-s['value_at_stop'])} (stop) "
                     f"or ≈ {_inr(-s['value_at_target'])} (target)")
    else:
        lines.append(f"Buy ≈ {_inr(s['entry_value'])} · SL ≈ {_inr(s['value_at_stop'])} · "
                     f"Target ≈ {_inr(s['value_at_target'])}")
    lines += [
        f"Index: entry {s['entry']:.1f} · SL {s['stop']:.1f} · target {s['target']:.1f}",
        f"Size: {s['lots']} lot(s) = {s['qty']} qty · risk ≈ {_inr(s['risk_inr'])}",
        "",
        f"<i>{html.escape(s['reason'])}</i> · confidence {s['confidence']:.0%}",
    ]
    if s.get("priced_by") == "model":
        lines.append("<i>Premiums are model estimates - check the live quote before ordering.</i>")
    return "\n".join(lines)


def format_close(s: dict[str, Any]) -> str:
    icon = {"TARGET": "✅", "STOP": "⛔", "TIME": "⏱"}.get(s["status"], "•")
    return (f"{icon} <b>{s['symbol']} {s['side']}</b> closed: {s['status']}\n"
            f"{html.escape(s.get('contract') or '')}\n"
            f"Index {s['entry']:.1f} → {s['exit_spot']:.1f} · est. P&L {_inr(s['pnl'])}")
