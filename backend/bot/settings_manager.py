"""Persist and apply wallet/strategy settings from the dashboard."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from bot.config import (
    NothingHappensConfig,
    _load_nothing_happens_config,
    _load_config_file,
    _validate_nothing_happens_config,
)
from bot.env_loader import backend_dir

_ENV_KEYS = (
    "BOT_MODE",
    "LIVE_TRADING_ENABLED",
    "DRY_RUN",
    "PRIVATE_KEY",
    "FUNDER_ADDRESS",
    "DATABASE_URL",
    "POLYGON_RPC_URL",
)

_STRATEGY_KEYS = (
    "max_entry_price",
    "cash_pct_per_trade",
    "min_trade_amount",
    "fixed_trade_amount",
    "allowed_slippage",
    "max_new_positions",
)


def _env_path() -> Path:
    return backend_dir() / ".env"


def _config_path() -> Path:
    from bot.config import _resolve_config_path

    return _resolve_config_path()


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return "••••••••"
    return f"{value[:6]}…{value[-4:]}"


class SettingsManager:
    """Thread-safe settings store backed by backend/.env and config.json."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reload_callbacks: list[Callable[[], None]] = []

    def on_reload(self, callback: Callable[[], None]) -> None:
        self._reload_callbacks.append(callback)

    def public_snapshot(self) -> dict[str, Any]:
        with self._lock:
            cfg = _load_config_file()
            strat = cfg.get("strategies", {}).get("nothing_happens", {})
            conn = cfg.get("connection", {})
            private_key = os.getenv("PRIVATE_KEY") or ""

            return {
                "bot_mode": (os.getenv("BOT_MODE") or "paper").strip().lower(),
                "live_trading_enabled": _parse_bool(os.getenv("LIVE_TRADING_ENABLED"), False),
                "dry_run": _parse_bool(os.getenv("DRY_RUN"), True),
                "demo_mode": _parse_bool(os.getenv("DEMO_MODE"), True),
                "private_key_set": bool(private_key),
                "private_key_preview": _mask_secret(private_key),
                "funder_address": os.getenv("FUNDER_ADDRESS") or "",
                "database_url_set": bool(os.getenv("DATABASE_URL")),
                "polygon_rpc_url_set": bool(os.getenv("POLYGON_RPC_URL")),
                "connection": {
                    "host": conn.get("host", "https://clob.polymarket.com"),
                    "chain_id": int(conn.get("chain_id", 137)),
                    "signature_type": int(conn.get("signature_type", 2)),
                },
                "strategy": {
                    "max_entry_price": float(strat.get("max_entry_price", 0.65)),
                    "cash_pct_per_trade": float(strat.get("cash_pct_per_trade", 0.02)),
                    "min_trade_amount": float(strat.get("min_trade_amount", 5)),
                    "fixed_trade_amount": float(strat.get("fixed_trade_amount", 0)),
                    "allowed_slippage": float(strat.get("allowed_slippage", 0.3)),
                    "max_new_positions": int(strat.get("max_new_positions", -1)),
                },
            }

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")

        with self._lock:
            env_updates: dict[str, str] = {}

            if "bot_mode" in payload:
                env_updates["BOT_MODE"] = str(payload["bot_mode"]).strip().lower()
            if "live_trading_enabled" in payload:
                env_updates["LIVE_TRADING_ENABLED"] = (
                    "true" if _parse_bool(payload["live_trading_enabled"], False) else "false"
                )
            if "dry_run" in payload:
                env_updates["DRY_RUN"] = "true" if _parse_bool(payload["dry_run"], True) else "false"
            if "demo_mode" in payload:
                demo = _parse_bool(payload["demo_mode"], True)
                env_updates["DEMO_MODE"] = "true" if demo else "false"
                if demo:
                    env_updates["BOT_MODE"] = "paper"
                    env_updates["DRY_RUN"] = "true"
                    env_updates["LIVE_TRADING_ENABLED"] = "false"
            if "private_key" in payload:
                key = str(payload["private_key"] or "").strip()
                if key:
                    env_updates["PRIVATE_KEY"] = key
            if "funder_address" in payload:
                env_updates["FUNDER_ADDRESS"] = str(payload["funder_address"] or "").strip()
            if "database_url" in payload:
                env_updates["DATABASE_URL"] = str(payload["database_url"] or "").strip()
            if "polygon_rpc_url" in payload:
                env_updates["POLYGON_RPC_URL"] = str(payload["polygon_rpc_url"] or "").strip()

            self._write_env(env_updates)
            for key, value in env_updates.items():
                if value:
                    os.environ[key] = value
                elif key in os.environ:
                    os.environ.pop(key, None)

            config_changed = False
            cfg = _load_config_file()
            connection = payload.get("connection")
            if isinstance(connection, dict):
                cfg.setdefault("connection", {}).update(
                    {k: connection[k] for k in ("host", "chain_id", "signature_type") if k in connection}
                )
                config_changed = True

            strategy = payload.get("strategy")
            if isinstance(strategy, dict):
                strat = cfg.setdefault("strategies", {}).setdefault("nothing_happens", {})
                for key in _STRATEGY_KEYS:
                    if key in strategy:
                        strat[key] = strategy[key]
                config_changed = True

            if config_changed:
                self._write_config(cfg)
                _, strategy_cfg = _load_nothing_happens_config(cfg)
                _validate_nothing_happens_config(strategy_cfg)

            for callback in self._reload_callbacks:
                callback()

            return {
                "ok": True,
                "message": "Settings saved and applied.",
                "snapshot": self.public_snapshot(),
            }

    def _write_env(self, updates: dict[str, str]) -> None:
        path = _env_path()
        existing: dict[str, str] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()

        existing.update(updates)
        lines = [
            "# Wallet and mode — managed via dashboard Settings",
            f"BOT_MODE={existing.get('BOT_MODE', 'paper')}",
            f"LIVE_TRADING_ENABLED={existing.get('LIVE_TRADING_ENABLED', 'false')}",
            f"DRY_RUN={existing.get('DRY_RUN', 'true')}",
            f"PRIVATE_KEY={existing.get('PRIVATE_KEY', '')}",
            f"FUNDER_ADDRESS={existing.get('FUNDER_ADDRESS', '')}",
            f"DATABASE_URL={existing.get('DATABASE_URL', '')}",
            f"POLYGON_RPC_URL={existing.get('POLYGON_RPC_URL', '')}",
            f"DEMO_MODE={existing.get('DEMO_MODE', os.getenv('DEMO_MODE', 'true'))}",
            f"DEMO_BALANCE={existing.get('DEMO_BALANCE', os.getenv('DEMO_BALANCE', '7535'))}",
            f"DEMO_SESSION_PNL={existing.get('DEMO_SESSION_PNL', os.getenv('DEMO_SESSION_PNL', '732'))}",
            f"API_PORT={existing.get('API_PORT', os.getenv('API_PORT', '8080'))}",
            f"CORS_ORIGINS={existing.get('CORS_ORIGINS', os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000'))}",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_config(self, cfg: dict[str, Any]) -> None:
        path = _config_path()
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


_settings_manager: SettingsManager | None = None


def get_settings_manager() -> SettingsManager:
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
