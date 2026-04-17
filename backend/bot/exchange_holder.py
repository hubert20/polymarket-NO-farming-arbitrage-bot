"""Mutable exchange reference for hot-reload after dashboard settings save."""

from __future__ import annotations

import threading
from typing import Any


class ExchangeHolder:
    def __init__(self, exchange: Any) -> None:
        self._lock = threading.Lock()
        self._exchange = exchange

    def get(self) -> Any:
        with self._lock:
            return self._exchange

    def set(self, exchange: Any) -> None:
        with self._lock:
            self._exchange = exchange


class ExchangeProxy:
    """Delegates attribute access to the current exchange inside a holder."""

    def __init__(self, holder: ExchangeHolder) -> None:
        self._holder = holder

    def __getattr__(self, name: str) -> Any:
        return getattr(self._holder.get(), name)
