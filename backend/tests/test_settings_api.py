"""Tests for settings API."""

import pytest

from bot.settings_manager import SettingsManager


def test_public_snapshot_has_strategy_keys(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(
        """{
  "connection": {"host": "https://clob.polymarket.com", "chain_id": 137, "signature_type": 2},
  "strategies": {
    "nothing_happens": {
      "max_entry_price": 0.65,
      "cash_pct_per_trade": 0.02,
      "min_trade_amount": 5
    }
  }
}""",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_MODE=paper\nDRY_RUN=true\nLIVE_TRADING_ENABLED=false\n", encoding="utf-8")

    monkeypatch.setenv("CONFIG_PATH", str(config))
    monkeypatch.chdir(tmp_path)

    import bot.settings_manager as sm

    manager = SettingsManager()
    monkeypatch.setattr(sm, "backend_dir", lambda: tmp_path)
    monkeypatch.setattr(sm, "_env_path", lambda: env_file)
    monkeypatch.setattr(sm, "_config_path", lambda: config)

    snap = manager.public_snapshot()
    assert snap["bot_mode"] == "paper"
    assert snap["strategy"]["max_entry_price"] == 0.65


@pytest.mark.asyncio
async def test_api_settings_get_endpoint():
    from bot.api_server import BotApiServer
    import aiohttp

    server = BotApiServer(port=0)
    app = aiohttp.web.Application()
    app.router.add_get("/api/settings", server._get_settings)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{port}/api/settings") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "strategy" in data
            assert "bot_mode" in data

    await runner.cleanup()
