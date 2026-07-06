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
from bot.env_loader import env_path

_ENV_KEYS = (
    "BOT_MODE",
    "LIVE_TRADING_ENABLED",
    "DRY_RUN",
    "DEMO_MODE",
    "DEMO_BALANCE",
    "DEMO_SESSION_PNL",
    "PRIVATE_KEY",
    "FUNDER_ADDRESS",
    "DATABASE_URL",
    "POLYGON_RPC_URL",
    "API_PORT",
    "CORS_ORIGINS",
)

_STRATEGY_KEYS = (
    "max_entry_price",
    "cash_pct_per_trade",
    "min_trade_amount",
    "fixed_trade_amount",
    "allowed_slippage",
    "max_new_positions",
)

_ENV_DEFAULTS: dict[str, str] = {
    "NEXT_PUBLIC_BOT_API_URL": "http://localhost:8080",
    "NEXT_PUBLIC_BOT_WS_URL": "ws://localhost:8080/ws",
    "API_PORT": "8080",
    "CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3000",
    "BOT_MODE": "paper",
    "LIVE_TRADING_ENABLED": "false",
    "DRY_RUN": "true",
    "DEMO_MODE": "true",
    "DEMO_BALANCE": "7535",
    "DEMO_SESSION_PNL": "732",
    "PRIVATE_KEY": "",
    "FUNDER_ADDRESS": "",
    "DATABASE_URL": "",
    "POLYGON_RPC_URL": "",
}

_ENV_SECTIONS: list[tuple[str, tuple[str, ...]]] = [
    (
        "# Dashboard (Next.js)",
        ("NEXT_PUBLIC_BOT_API_URL", "NEXT_PUBLIC_BOT_WS_URL"),
    ),
    (
        "# Bot API",
        ("API_PORT", "CORS_ORIGINS"),
    ),
    (
        "# Mode",
        (
            "BOT_MODE",
            "LIVE_TRADING_ENABLED",
            "DRY_RUN",
            "DEMO_MODE",
            "DEMO_BALANCE",
            "DEMO_SESSION_PNL",
        ),
    ),
    (
        "# Wallet (live trading)",
        ("PRIVATE_KEY", "FUNDER_ADDRESS", "DATABASE_URL", "POLYGON_RPC_URL"),
    ),
]


def _config_path() -> Path:
    from bot.config import _resolve_config_path

    return _resolve_config_path()


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


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
    """Thread-safe settings store backed by root `.env` and backend/config.json."""

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
        path = env_path()
        existing = _parse_env_file(path)
        existing.update(updates)
        for key, value in _ENV_DEFAULTS.items():
            existing.setdefault(key, value)

        lines = [
            "# Polymarket NO Farming Bot — single root .env (backend + dashboard)",
            "# Wallet and mode — also editable from dashboard Settings",
            "",
        ]
        written: set[str] = set()
        for header, keys in _ENV_SECTIONS:
            section_keys = [key for key in keys if key in existing]
            if not section_keys:
                continue
            lines.append(header)
            for key in section_keys:
                lines.append(f"{key}={existing[key]}")
                written.add(key)
            lines.append("")

        extras = sorted(key for key in existing if key not in written)
        if extras:
            lines.append("# Other")
            for key in extras:
                lines.append(f"{key}={existing[key]}")
            lines.append("")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _write_config(self, cfg: dict[str, Any]) -> None:
        path = _config_path()
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


_settings_manager: SettingsManager | None = None


def get_settings_manager() -> SettingsManager:
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
