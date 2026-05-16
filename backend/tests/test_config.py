import json

import pytest

from bot.config import load_nothing_happens_config


def _write_config(tmp_path, payload) -> str:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))
    return str(path)


def _base_config(*, connection=None, strategy_cfg=None):
    payload = {
        "connection": {
            "host": "https://clob.polymarket.com",
            "chain_id": 137,
            "signature_type": 2,
        },
        "strategies": {
            "nothing_happens": strategy_cfg or {},
        },
    }
    if connection:
        payload["connection"].update(connection)
    return payload


def test_load_nothing_happens_config_fails_without_config_file(monkeypatch) -> None:
    monkeypatch.setenv("CONFIG_PATH", "/nonexistent/config.json")
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_nothing_happens_config()


def test_load_nothing_happens_config_requires_strategy_section(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONFIG_PATH", _write_config(tmp_path, {"connection": {}}))
    with pytest.raises(ValueError, match="Missing strategies.nothing_happens"):
        load_nothing_happens_config()


def test_load_nothing_happens_config_rejects_unsupported_strategy_selector(
    tmp_path,
    monkeypatch,
) -> None:
    payload = _base_config()
    payload["strategy"] = "instant_gap"
    monkeypatch.setenv("CONFIG_PATH", _write_config(tmp_path, payload))
    with pytest.raises(ValueError, match="Unsupported runtime strategy"):
        load_nothing_happens_config()


def test_load_nothing_happens_config_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONFIG_PATH", _write_config(tmp_path, _base_config()))
    exchange, strategy = load_nothing_happens_config()

    assert exchange.host == "https://clob.polymarket.com"
    assert exchange.chain_id == 137
    assert strategy.market_refresh_interval_sec == 600
    assert strategy.cash_pct_per_trade == 0.02
    assert strategy.fixed_trade_amount == 0.0
    assert strategy.max_entry_price == 0.65
    assert strategy.max_new_positions == -1


def test_load_nothing_happens_config_applies_env_overrides(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONFIG_PATH", _write_config(tmp_path, _base_config()))
    monkeypatch.setenv("PM_NH_FIXED_TRADE_AMOUNT_USD", "5")
    monkeypatch.setenv("PM_NH_ORDER_DISPATCH_INTERVAL_SEC", "75")
    monkeypatch.setenv("PM_NH_MAX_NEW_POSITIONS", "2")
    monkeypatch.setenv("PM_NH_SHUTDOWN_ON_MAX_NEW_POSITIONS", "true")

    exchange, strategy = load_nothing_happens_config()

    assert exchange.host == "https://clob.polymarket.com"
    assert strategy.fixed_trade_amount == 5.0
    assert strategy.order_dispatch_interval_sec == 75
    assert strategy.max_new_positions == 2
    assert strategy.shutdown_on_max_new_positions is True


def test_load_nothing_happens_config_validates_bounds(tmp_path, monkeypatch) -> None:
    payload = _base_config(
        strategy_cfg={
            "cash_pct_per_trade": 0,
            "max_entry_price": 1.2,
        }
    )
    monkeypatch.setenv("CONFIG_PATH", _write_config(tmp_path, payload))
    with pytest.raises(ValueError, match="cash_pct_per_trade"):
        load_nothing_happens_config()


def test_load_nothing_happens_config_accepts_negative_one_for_unbounded_positions(
    tmp_path,
    monkeypatch,
) -> None:
    payload = _base_config(strategy_cfg={"max_new_positions": -1})
    monkeypatch.setenv("CONFIG_PATH", _write_config(tmp_path, payload))

    _, strategy = load_nothing_happens_config()

    assert strategy.max_new_positions == -1


def test_load_nothing_happens_config_rejects_less_than_negative_one(
    tmp_path,
    monkeypatch,
) -> None:
    payload = _base_config(strategy_cfg={"max_new_positions": -2})
    monkeypatch.setenv("CONFIG_PATH", _write_config(tmp_path, payload))
    with pytest.raises(ValueError, match="max_new_positions must be >= -1"):
        load_nothing_happens_config()


def test_load_nothing_happens_config_requires_private_key_when_live_send_enabled(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CONFIG_PATH", _write_config(tmp_path, _base_config()))
    monkeypatch.setenv("BOT_MODE", "live")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    with pytest.raises(ValueError, match="PRIVATE_KEY"):
        load_nothing_happens_config()


def test_load_nothing_happens_config_requires_funder_for_proxy_wallets(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CONFIG_PATH",
        _write_config(tmp_path, _base_config(connection={"signature_type": 2})),
    )
    monkeypatch.setenv("BOT_MODE", "live")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("PRIVATE_KEY", "0xabc")
    with pytest.raises(ValueError, match="FUNDER_ADDRESS"):
        load_nothing_happens_config()
