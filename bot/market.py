from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    slug: str
    condition_id: str
    up_token_id: str
    down_token_id: str
    interval_start: int
    price_to_beat: float | None = None
    price_to_beat_source: str = ""
