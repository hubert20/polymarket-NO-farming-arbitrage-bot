"""Smoke tests for the bot API server."""

import asyncio

import aiohttp
import pytest

from bot.api_server import BotApiServer
from bot.nothing_happens_control import NothingHappensControlState
from bot.portfolio_state import PortfolioState


def _make_portfolio_state() -> PortfolioState:
    portfolio_state = PortfolioState()
    portfolio_state.update(
        updated_at_us=1,
        monitored_markets=12,
        eligible_markets=10,
        in_range_markets=3,
        positions=[],
        cash_balance=42.0,
        last_market_refresh_ts=1.0,
        last_position_sync_ts=1.0,
        last_price_cycle_ts=1.0,
        last_error="",
    )
    return portfolio_state


def test_api_server_creates():
    server = BotApiServer(port=0)
    assert server.port == 0
    assert server._clients == set()


def test_api_force_portfolio_snapshot_replays_latest_state():
    portfolio_state = _make_portfolio_state()
    server = BotApiServer(port=0, portfolio_state=portfolio_state)

    first = server._make_portfolio_message(force=True)
    second = server._make_portfolio_message(force=True)

    assert first is not None
    assert second is not None
    assert first["cash_balance"] == 42.0
    assert first["in_range_markets"] == 3


@pytest.mark.asyncio
async def test_api_health_endpoint():
    server = BotApiServer(port=0)
    app = aiohttp.web.Application()
    app.router.add_get("/health", server._health)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{port}/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"

    await runner.cleanup()


@pytest.mark.asyncio
async def test_api_websocket_sends_initial_portfolio():
    server = BotApiServer(port=0, portfolio_state=_make_portfolio_state())
    app = aiohttp.web.Application()
    app.router.add_get("/ws", server._ws_handler)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
            message = await asyncio.wait_for(ws.receive_json(), timeout=2)
            assert message["type"] == "portfolio"
            assert message["cash_balance"] == 42.0
            assert message["in_range_markets"] == 3
            await ws.close()

    await runner.cleanup()


@pytest.mark.asyncio
async def test_api_websocket_rejects_target_updates():
    control_state = NothingHappensControlState()
    control_state.update_status(
        current_open_positions=0,
        pending_entry_count=0,
        remaining_capacity=None,
        opened_this_run=0,
    )
    server = BotApiServer(
        port=0,
        portfolio_state=_make_portfolio_state(),
        nothing_happens_control=control_state,
    )
    app = aiohttp.web.Application()
    app.router.add_get("/ws", server._ws_handler)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
            initial = await asyncio.wait_for(ws.receive_json(), timeout=2)
            assert initial["type"] == "portfolio"
            assert initial["controls_enabled"] is True
            await ws.send_json({"type": "set_position_target", "target_open_positions": 17})
            ack = await asyncio.wait_for(ws.receive_json(), timeout=2)
            assert ack == {
                "type": "control_ack",
                "ok": False,
                "error": "controls_disabled",
            }
            await ws.close()

    assert control_state.snapshot().target_open_positions is None
    await runner.cleanup()
