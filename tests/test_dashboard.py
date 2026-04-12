"""Smoke tests for dashboard server."""

import asyncio

import aiohttp
import pytest

from bot.dashboard import DashboardServer
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


def test_dashboard_creates():
    server = DashboardServer(port=0)
    assert server.port == 0
    assert server._clients == set()


def test_dashboard_force_portfolio_snapshot_replays_latest_state():
    portfolio_state = _make_portfolio_state()
    server = DashboardServer(port=0, portfolio_state=portfolio_state)

    first = server._make_portfolio_message(force=True)
    second = server._make_portfolio_message(force=True)

    assert first is not None
    assert second is not None
    assert first["cash_balance"] == 42.0
    assert first["in_range_markets"] == 3
    assert second["cash_balance"] == 42.0
    assert second["in_range_markets"] == 3


@pytest.mark.asyncio
async def test_dashboard_http_serves_html():
    server = DashboardServer(port=0)
    app = aiohttp.web.Application()
    app.router.add_get("/", server._index)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{port}/") as resp:
            assert resp.status == 200
            text = await resp.text()
            assert "Dashboard" in text
            assert "Open Positions" in text
            assert "In Range" in text

    await runner.cleanup()


@pytest.mark.asyncio
async def test_dashboard_http_serves_background_image():
    server = DashboardServer(port=0)
    app = aiohttp.web.Application()
    app.router.add_get("/nothingeverhappens.svg", server._background_image)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{port}/nothingeverhappens.svg") as resp:
            assert resp.status == 200
            assert resp.headers["Content-Type"].startswith("image/svg+xml")
            text = await resp.text()
            assert "<svg" in text

    await runner.cleanup()


@pytest.mark.asyncio
async def test_dashboard_websocket_sends_initial_portfolio():
    server = DashboardServer(port=0, portfolio_state=_make_portfolio_state())
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
async def test_dashboard_websocket_rejects_nothing_happens_target_updates():
    control_state = NothingHappensControlState()
    control_state.update_status(
        current_open_positions=0,
        pending_entry_count=0,
        remaining_capacity=None,
        opened_this_run=0,
    )
    server = DashboardServer(
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
