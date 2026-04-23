"""Shared live controls for the nothing-happens strategy."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class NothingHappensControlSnapshot:
    updated_at_us: int = 0
    target_open_positions: int | None = None
    current_open_positions: int = 0
    pending_entry_count: int = 0
    remaining_capacity: int | None = None
    opened_this_run: int = 0


class NothingHappensControlState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._snapshot = NothingHappensControlSnapshot()
        self._target_is_user_override = False

    def version(self) -> int:
        with self._lock:
            return self._version

    def snapshot(self) -> NothingHappensControlSnapshot:
        with self._lock:
            return self._snapshot

    def is_target_user_override(self) -> bool:
        with self._lock:
            return self._target_is_user_override

    def ensure_target_open_positions(self, target: int | None) -> NothingHappensControlSnapshot:
        with self._lock:
            if self._target_is_user_override or target is None:
                return self._snapshot
            normalized_target = int(target)
            if self._snapshot.target_open_positions == normalized_target:
                return self._snapshot
            self._snapshot = NothingHappensControlSnapshot(
                updated_at_us=int(time.time() * 1_000_000),
                target_open_positions=normalized_target,
                current_open_positions=self._snapshot.current_open_positions,
                pending_entry_count=self._snapshot.pending_entry_count,
                remaining_capacity=self._snapshot.remaining_capacity,
                opened_this_run=self._snapshot.opened_this_run,
            )
            self._version += 1
            return self._snapshot

    def set_target_open_positions(self, target: int | None) -> NothingHappensControlSnapshot:
        if target is not None and target < 0:
            raise ValueError("target_open_positions must be >= 0")
        with self._lock:
            normalized_target = None if target is None else int(target)
            self._target_is_user_override = normalized_target is not None
            self._snapshot = NothingHappensControlSnapshot(
                updated_at_us=int(time.time() * 1_000_000),
                target_open_positions=normalized_target,
                current_open_positions=self._snapshot.current_open_positions,
                pending_entry_count=self._snapshot.pending_entry_count,
                remaining_capacity=self._snapshot.remaining_capacity,
                opened_this_run=self._snapshot.opened_this_run,
            )
            self._version += 1
            return self._snapshot

    def update_status(
        self,
        *,
        current_open_positions: int,
        pending_entry_count: int,
        remaining_capacity: int | None,
        opened_this_run: int,
    ) -> NothingHappensControlSnapshot:
        with self._lock:
            self._snapshot = NothingHappensControlSnapshot(
                updated_at_us=int(time.time() * 1_000_000),
                target_open_positions=self._snapshot.target_open_positions,
                current_open_positions=int(current_open_positions),
                pending_entry_count=int(pending_entry_count),
                remaining_capacity=None if remaining_capacity is None else int(remaining_capacity),
                opened_this_run=int(opened_this_run),
            )
            self._version += 1
            return self._snapshot
