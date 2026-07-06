"""WebSocket + REST API for the Next.js dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque

from aiohttp import web

from bot.nothing_happens_control import NothingHappensControlState
from bot.settings_manager import get_settings_manager
from bot.demo_mode import (
    demo_balance,
    demo_session_pnl_message,
    demo_session_starting_balance,
    is_demo_mode,
)

logger = logging.getLogger(__name__)

BALANCE_POLL_INTERVAL_SEC = 30.0
BALANCE_TIMEOUT_SEC = 10.0
RESOLUTION_POLL_INTERVAL_SEC = 15.0
TRADE_HISTORY_LIMIT = 1000
BALANCE_HISTORY_LIMIT = 2880


def _allowed_origins() -> set[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def _is_allowed_origin(origin: str) -> bool:
    if not origin:
        return True
    if origin in _allowed_origins():
        return True
    try:
        from urllib.parse import urlparse

        parsed = urlparse(origin)
        if parsed.port == 3000 and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
            "[::1]",
            "0.0.0.0",
        }:
            return True
    except Exception:
        pass
    return False


@web.middleware
async def cors_middleware(request: web.Request, handler):
    origin = request.headers.get("Origin", "")
    allowed = _allowed_origins()

    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)

    if origin in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    elif _is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


class BotApiServer:
    """Streams bot state to dashboard clients over WebSocket."""

    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        exchange=None,
        exchange_holder=None,
        portfolio_state=None,
        nothing_happens_control: NothingHappensControlState | None = None,
    ):
        self.host = host
        self.port = port
        self._exchange = exchange
        self._exchange_holder = exchange_holder
        self._portfolio_state = portfolio_state
        self._nothing_happens_control = nothing_happens_control
        self._clients: set[web.WebSocketResponse] = set()
        self._last_portfolio_version = -1
        self._last_nothing_happens_control_version = -1
        self._ledger_path = os.getenv("TRADE_LEDGER_PATH", "trades.jsonl")
        self._ledger_pos = 0
        self._trade_history: deque[dict] = deque(maxlen=TRADE_HISTORY_LIMIT)
        self._starting_balance: float | None = None
        self._current_balance: float | None = None
        self._last_balance_poll = 0.0
        self._balance_history: deque[tuple[float, float]] = deque(maxlen=BALANCE_HISTORY_LIMIT)
        self._resolutions: dict[str, str] = {}
        self._pending_resolution_slugs: list[str] = []
        self._last_resolution_poll = 0.0
        self._seed_demo_balance_state()

    def _seed_demo_balance_state(self) -> None:
        if not is_demo_mode():
            return
        self._starting_balance = demo_session_starting_balance()
        self._current_balance = demo_balance()
        now = time.time()
        if self._balance_history:
            return
        start = self._starting_balance
        end = self._current_balance
        for i in range(12):
            ts = now - (11 - i) * 30 * 60
            bal = start + (end - start) * (i / 11)
            self._balance_history.append((ts, round(bal, 2)))

    async def _health(self, _request: web.Request) -> web.Response:
        dry_raw = (os.getenv("DRY_RUN") or "true").strip().lower()
        live_raw = (os.getenv("LIVE_TRADING_ENABLED") or "false").strip().lower()
        return web.json_response(
            {
                "status": "ok",
                "service": "no-farming-bot",
                "bot_mode": (os.getenv("BOT_MODE") or "paper").strip().lower(),
                "dry_run": dry_raw in {"1", "true", "yes", "on"},
                "live_trading_enabled": live_raw in {"1", "true", "yes", "on"},
                "demo_mode": is_demo_mode(),
                "uptime_clients": len(self._clients),
            }
        )

    def _effective_portfolio_message(self, *, force: bool = False) -> dict | None:
        return self._make_portfolio_message(force=force)

    async def _status(self, _request: web.Request) -> web.Response:
        portfolio = self._make_portfolio_message(force=True)
        payload: dict = {
            "portfolio": portfolio,
            "session_pnl": demo_session_pnl_message() if is_demo_mode() else (
                self._make_pnl_message() if self._starting_balance is not None else None
            ),
            "balance_history": [
                {"ts": ts * 1000, "balance": round(balance, 2)}
                for ts, balance in self._balance_history
            ],
            "trades": list(self._trade_history)[-500:],
            "resolutions": [
                {"market_slug": slug, "winner": winner}
                for slug, winner in self._resolutions.items()
            ],
        }
        return web.json_response(payload)

    def _active_exchange(self):
        if self._exchange_holder is not None:
            return self._exchange_holder.get()
        return self._exchange

    async def _get_settings(self, _request: web.Request) -> web.Response:
        return web.json_response(get_settings_manager().public_snapshot())

    async def _post_settings(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        try:
            result = get_settings_manager().apply(payload)
            return web.json_response(result)
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.exception("settings_apply_failed")
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        origin = request.headers.get("Origin", "")
        if origin and not _is_allowed_origin(origin):
            raise web.HTTPForbidden(text="origin not allowed")

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        logger.info("Dashboard client connected (%d total)", len(self._clients))
        await self._send_initial(ws)
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_message(ws, msg.data)
        finally:
            self._clients.discard(ws)
            logger.info("Dashboard client disconnected (%d remaining)", len(self._clients))
        return ws

    async def _handle_ws_message(self, ws: web.WebSocketResponse, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await self._send_to(ws, {"type": "control_ack", "ok": False, "error": "invalid_json"})
            return
        if not isinstance(payload, dict):
            await self._send_to(ws, {"type": "control_ack", "ok": False, "error": "invalid_payload"})
            return
        if payload.get("type") == "set_position_target":
            await self._send_to(ws, {"type": "control_ack", "ok": False, "error": "controls_disabled"})

    async def _send_to(self, ws: web.WebSocketResponse, data: dict) -> None:
        try:
            await ws.send_str(json.dumps(data))
        except Exception:
            self._clients.discard(ws)

    async def _broadcast(self, data: dict) -> None:
        if not self._clients:
            return
        message = json.dumps(data)
        dead: set[web.WebSocketResponse] = set()
        for ws in self._clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def _send_initial(self, ws: web.WebSocketResponse) -> None:
        portfolio_message = self._effective_portfolio_message(force=True)
        if portfolio_message is not None:
            await self._send_to(ws, portfolio_message)

        if is_demo_mode():
            await self._send_to(ws, demo_session_pnl_message())
        elif self._starting_balance is not None and self._current_balance is not None:
            await self._send_to(ws, self._make_pnl_message())
        if self._balance_history:
            await self._send_to(
                ws,
                {
                    "type": "balance_history",
                    "points": [
                        {"ts": ts * 1000, "balance": round(balance, 2)}
                        for ts, balance in self._balance_history
                    ],
                },
            )
        for trade in list(self._trade_history)[-500:]:
            await self._send_to(ws, trade)
        for slug, winner in self._resolutions.items():
            await self._send_to(
                ws,
                {"type": "resolution", "market_slug": slug, "winner": winner},
            )

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("API poll error: %s", exc)
            await asyncio.sleep(0.25)

    async def _poll_once(self) -> None:
        portfolio_message = self._effective_portfolio_message()
        if portfolio_message is not None:
            await self._broadcast(portfolio_message)
        await self._poll_trades()
        await self._poll_balance()
        await self._poll_resolutions()

    def _make_portfolio_message(self, *, force: bool = False) -> dict | None:
        if self._portfolio_state is None:
            return None
        version = self._portfolio_state.version()
        control_version = (
            self._nothing_happens_control.version()
            if self._nothing_happens_control is not None
            else -1
        )
        if (
            not force
            and version == self._last_portfolio_version
            and control_version == self._last_nothing_happens_control_version
        ):
            return None
        self._last_portfolio_version = version
        self._last_nothing_happens_control_version = control_version
        snapshot = self._portfolio_state.snapshot()
        control_snapshot = (
            self._nothing_happens_control.snapshot()
            if self._nothing_happens_control is not None
            else None
        )
        return {
            "type": "portfolio",
            "updated_at_us": snapshot.updated_at_us,
            "monitored_markets": snapshot.monitored_markets,
            "eligible_markets": snapshot.eligible_markets,
            "in_range_markets": snapshot.in_range_markets,
            "cash_balance": snapshot.cash_balance,
            "last_market_refresh_ts": snapshot.last_market_refresh_ts,
            "last_position_sync_ts": snapshot.last_position_sync_ts,
            "last_price_cycle_ts": snapshot.last_price_cycle_ts,
            "last_error": snapshot.last_error,
            "target_open_positions": (
                control_snapshot.target_open_positions if control_snapshot is not None else None
            ),
            "pending_entry_count": (
                control_snapshot.pending_entry_count if control_snapshot is not None else 0
            ),
            "remaining_position_capacity": (
                control_snapshot.remaining_capacity if control_snapshot is not None else None
            ),
            "opened_this_run": (
                control_snapshot.opened_this_run if control_snapshot is not None else 0
            ),
            "controls_enabled": control_snapshot is not None,
            "demo_mode": is_demo_mode(),
            "positions": [
                {
                    "slug": position.slug,
                    "title": position.title,
                    "outcome": position.outcome,
                    "asset": position.asset,
                    "condition_id": position.condition_id,
                    "size": round(position.size, 6),
                    "avg_price": round(position.avg_price, 6),
                    "initial_value": round(position.initial_value, 6),
                    "current_price": round(position.current_price, 6),
                    "current_value": round(position.current_value, 6),
                    "pnl_usd": round(position.pnl_usd, 6),
                    "pnl_pct": round(position.pnl_pct, 6),
                    "end_date": position.end_date,
                    "eta_seconds": round(position.eta_seconds, 3),
                    "source": position.source,
                }
                for position in snapshot.positions
            ],
        }

    async def _poll_trades(self) -> None:
        try:
            if not os.path.exists(self._ledger_path):
                return
            with open(self._ledger_path, "r") as f:
                f.seek(self._ledger_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    trade_msg = {"type": "bot_trade", **record}
                    self._trade_history.append(trade_msg)
                    await self._broadcast(trade_msg)
                self._ledger_pos = f.tell()
        except Exception as exc:
            logger.debug("Trade ledger poll error: %s", exc)

    def _make_pnl_message(self) -> dict:
        if is_demo_mode():
            return demo_session_pnl_message()
        pnl_usd = (self._current_balance or 0.0) - (self._starting_balance or 0.0)
        pnl_pct = (
            (pnl_usd / self._starting_balance * 100.0)
            if self._starting_balance and self._starting_balance > 0
            else 0.0
        )
        return {
            "type": "session_pnl",
            "starting_balance": round(self._starting_balance or 0.0, 2),
            "current_balance": round(self._current_balance or 0.0, 2),
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 2),
        }

    async def _poll_balance(self) -> None:
        if is_demo_mode():
            loop_now = asyncio.get_running_loop().time()
            if loop_now - self._last_balance_poll < BALANCE_POLL_INTERVAL_SEC:
                return
            self._last_balance_poll = loop_now
            self._starting_balance = demo_session_starting_balance()
            self._current_balance = demo_balance()
            ts_sec = time.time()
            self._balance_history.append((ts_sec, self._current_balance))
            await self._broadcast(demo_session_pnl_message())
            await self._broadcast(
                {
                    "type": "balance_point",
                    "ts": ts_sec * 1000,
                    "balance": round(self._current_balance, 2),
                }
            )
            return

        exchange = self._active_exchange()
        if exchange is None:
            return
        loop_now = asyncio.get_running_loop().time()
        if loop_now - self._last_balance_poll < BALANCE_POLL_INTERVAL_SEC:
            return
        self._last_balance_poll = loop_now
        try:
            balance = await asyncio.wait_for(
                asyncio.to_thread(exchange.get_collateral_balance),
                timeout=BALANCE_TIMEOUT_SEC,
            )
            if self._starting_balance is None:
                self._starting_balance = balance
                logger.info(
                    "api_starting_balance",
                    extra={"balance": round(balance, 2)},
                )
            self._current_balance = balance
            ts_sec = time.time()
            self._balance_history.append((ts_sec, balance))
            await self._broadcast(self._make_pnl_message())
            await self._broadcast(
                {
                    "type": "balance_point",
                    "ts": ts_sec * 1000,
                    "balance": round(balance, 2),
                }
            )
        except Exception as exc:
            logger.debug("API balance poll failed: %s", exc)

    async def _poll_resolutions(self) -> None:
        loop_now = asyncio.get_running_loop().time()
        if loop_now - self._last_resolution_poll < RESOLUTION_POLL_INTERVAL_SEC:
            return
        self._last_resolution_poll = loop_now

        for trade in self._trade_history:
            slug = trade.get("market_slug", "")
            if slug and slug not in self._resolutions and slug not in self._pending_resolution_slugs:
                self._pending_resolution_slugs.append(slug)

        if not self._pending_resolution_slugs:
            return

        from bot.live_recovery import _check_gamma_resolution

        for slug in self._pending_resolution_slugs[:5]:
            try:
                winner = await _check_gamma_resolution(slug)
                if winner is None:
                    continue
                display_winner = winner.capitalize()
                self._resolutions[slug] = display_winner
                self._pending_resolution_slugs.remove(slug)
                await self._broadcast(
                    {
                        "type": "resolution",
                        "market_slug": slug,
                        "winner": display_winner,
                    }
                )
                logger.info("Resolution: %s -> %s", slug, display_winner)
            except Exception as exc:
                logger.debug("Resolution fetch failed for %s: %s", slug, exc)

    async def run(self) -> None:
        app = web.Application(middlewares=[cors_middleware])
        app.router.add_get("/health", self._health)
        app.router.add_get("/api/status", self._status)
        app.router.add_get("/api/settings", self._get_settings)
        app.router.add_post("/api/settings", self._post_settings)
        app.router.add_get("/ws", self._ws_handler)

        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("Bot API at http://%s:%d (ws /ws, status /api/status)", self.host, self.port)

        try:
            await self._poll_loop()
        finally:
            await runner.cleanup()
