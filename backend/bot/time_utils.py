from __future__ import annotations

from datetime import datetime, timezone


def parse_venue_timestamp(value: str | int | float | None) -> datetime | None:
    if value in {None, ""}:
        return None

    if isinstance(value, (int, float)):
        return _epoch_to_datetime(float(value))

    raw = str(value).strip()
    if not raw:
        return None

    try:
        return _epoch_to_datetime(float(raw))
    except ValueError:
        pass

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_epoch_seconds(value: str | int | float | datetime | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())

    parsed = parse_venue_timestamp(value)
    if parsed is None:
        return None
    return int(parsed.timestamp())


def _epoch_to_datetime(raw_value: float) -> datetime:
    if abs(raw_value) >= 1_000_000_000_000:
        raw_value = raw_value / 1000.0
    return datetime.fromtimestamp(raw_value, tz=timezone.utc)
