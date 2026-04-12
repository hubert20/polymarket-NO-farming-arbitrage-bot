"""Standalone yes/no market discovery shared by scripts and live runtime."""

from __future__ import annotations

import asyncio
import ctypes
import gc
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiohttp

logger = logging.getLogger(__name__)
try:
    _LIBC = ctypes.CDLL("libc.so.6")
except OSError:
    _LIBC = None

GAMMA_API = "https://gamma-api.polymarket.com"
PAGE_LIMIT = 100
DEFAULT_MAX_END_DATE_MONTHS = 3
PAGE_DELAY_SEC = 0.1
PAGE_BURST_SIZE = 20
PAGE_BURST_PAUSE_SEC = 2.0
PAGE_MAX_RETRIES = 8
PAGE_RETRY_BASE_DELAY_SEC = 1.0
PAGE_RETRY_MAX_DELAY_SEC = 30.0
GC_COLLECT_INTERVAL_PAGES = 20

EXCLUDED_KEYWORDS = {
    # Crypto
    "crypto",
    "cryptocurrency",
    "bitcoin",
    "ethereum",
    "defi",
    "nft",
    "solana",
    "polygon",
    "blockchain",
    "token launch",
    "launch a token",
    "airdrop",
    "stablecoin",
    "memecoin",
    "altcoin",
    "btc ",
    "xrp",
    "bnb",
    " sol ",
    "cardano",
    "dogecoin",
    "doge",
    # Finance
    "finance",
    "stocks",
    "forex",
    "commodities",
    "fed rate",
    "fed funds",
    "interest rate",
    "treasury",
    "inflation",
    "gdp",
    "earnings",
    "ipo",
    "etf",
    "s&p 500",
    "s&p500",
    "nasdaq",
    "dow jones",
    "ftse",
    "bond yield",
    "market cap",
    "trading volume",
    "up or down",
    # Sports
    "mlb",
    "nba",
    "nfl",
    "nhl",
    "baseball",
    "basketball",
    "football",
    "hockey",
    "soccer",
    "mls",
    "premier league",
    "la liga",
    "serie a",
    "bundesliga",
    "ligue 1",
    "champions league",
    "uefa",
    "fifa",
    "tennis",
    "golf",
    "pga",
    "ufc",
    "mma",
    "boxing",
    "f1",
    "formula 1",
    "nascar",
    "cricket",
    "ipl",
    "rugby",
    "olympics",
    "world series",
    "super bowl",
    "march madness",
    "stanley cup",
    "world cup",
    "ncaab",
    "ncaa",
    "college basketball",
    "college football",
    "table tennis",
    "chess",
    "pickleball",
    "esports",
    "e-sports",
}

EXCLUDED_TITLE_PHRASES = {
    "nothing ever happens",
}


class GammaMarketFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class StandaloneMarket:
    question: str
    slug: str
    condition_id: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    min_order_size: float
    end_date: str
    end_ts: float
    category: str
    event_slug: str


def _get_event_slug(market: dict) -> str:
    events = market.get("events") or []
    if events and isinstance(events, list):
        return events[0].get("slug", "") if isinstance(events[0], dict) else ""
    return ""


def _load_json_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _parse_iso_ts(value: str) -> float:
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return 0.0
    return dt.timestamp()


def _is_excluded_category(market: dict) -> bool:
    tags = market.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = [tags]
    for tag in tags:
        label = (
            (tag.get("label") or tag.get("name") or "").lower()
            if isinstance(tag, dict)
            else str(tag).lower()
        )
        for keyword in EXCLUDED_KEYWORDS:
            if keyword in label:
                return True

    for field in ("groupItemTitle", "category", "question", "description"):
        value = (market.get(field) or "").lower()
        for keyword in EXCLUDED_KEYWORDS:
            if keyword in value:
                return True
    return False


def _is_binary_yes_no(market: dict) -> bool:
    outcomes = _load_json_list(market.get("outcomes"))
    if len(outcomes) != 2:
        return False
    labels = {str(outcome).strip().lower() for outcome in outcomes}
    return labels == {"yes", "no"}


def _has_excluded_title_phrase(market: dict) -> bool:
    for field in ("question", "groupItemTitle"):
        value = str(market.get(field) or "").lower()
        if any(phrase in value for phrase in EXCLUDED_TITLE_PHRASES):
            return True
    return False


def _ends_within_window(market: dict, *, max_end_date_months: int) -> bool:
    end_dt = _parse_iso_ts(market.get("endDate") or market.get("endDateIso") or "")
    if end_dt <= 0:
        return False
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=max_end_date_months * 30)
    end = datetime.fromtimestamp(end_dt, tz=timezone.utc)
    return now <= end <= cutoff


def _is_standalone(market: dict, event_counts: Counter) -> bool:
    if market.get("negRisk"):
        return False
    event_slug = _get_event_slug(market)
    if event_slug and event_counts.get(event_slug, 0) > 1:
        return False
    return True


def _is_sports_market(market: dict) -> bool:
    if market.get("sportsMarketType"):
        return True
    if market.get("gameStartTime"):
        return True
    if str(market.get("feeType") or "").startswith("sports"):
        return True
    events = market.get("events") or []
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict) and event.get("seriesSlug"):
                return True
    return False


def _passes_candidate_filters(market: dict, *, max_end_date_months: int) -> bool:
    if not _is_binary_yes_no(market):
        return False
    if _is_sports_market(market):
        return False
    if _has_excluded_title_phrase(market):
        return False
    if _is_excluded_category(market):
        return False
    if not _ends_within_window(market, max_end_date_months=max_end_date_months):
        return False
    return True


def _parse_probability_pair(value) -> tuple[float, float]:
    prices = _load_json_list(value)
    if len(prices) < 2:
        return 0.0, 0.0
    try:
        return float(prices[0]), float(prices[1])
    except (TypeError, ValueError):
        return 0.0, 0.0


def _parse_token_pair(market: dict) -> tuple[str, str]:
    token_ids = _load_json_list(market.get("clobTokenIds"))
    outcomes = _load_json_list(market.get("outcomes"))
    if len(token_ids) < 2 or len(outcomes) < 2:
        return "", ""
    yes_token = ""
    no_token = ""
    for index, outcome in enumerate(outcomes):
        label = str(outcome).strip().lower()
        if label == "yes":
            yes_token = str(token_ids[index])
        elif label == "no":
            no_token = str(token_ids[index])
    return yes_token, no_token


def build_standalone_market(market: dict) -> StandaloneMarket | None:
    yes_token_id, no_token_id = _parse_token_pair(market)
    if not yes_token_id or not no_token_id:
        return None
    yes_price, no_price = _parse_probability_pair(market.get("outcomePrices"))
    end_date = str(market.get("endDate") or market.get("endDateIso") or "")
    return StandaloneMarket(
        question=str(market.get("question") or ""),
        slug=str(market.get("slug") or ""),
        condition_id=str(market.get("conditionId") or ""),
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
        yes_price=yes_price,
        no_price=no_price,
        volume=float(market.get("volume") or 0.0),
        liquidity=float(market.get("liquidity") or 0.0),
        min_order_size=float(market.get("orderMinSize") or 0.0),
        end_date=end_date,
        end_ts=_parse_iso_ts(end_date),
        category=str(market.get("groupItemTitle") or market.get("category") or ""),
        event_slug=_get_event_slug(market),
    )


async def fetch_all_open_markets(session: aiohttp.ClientSession) -> list[dict]:
    all_markets: list[dict] = []
    pages_processed = 0
    async for batch in _iter_open_market_batches(session):
        all_markets.extend(batch)
        pages_processed += 1
        _maybe_collect_gc(pages_processed)
    return all_markets


def _parse_retry_after_seconds(headers) -> float | None:
    if not headers:
        return None
    try:
        raw = headers.get("Retry-After")
    except AttributeError:
        raw = None
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


async def _iter_open_market_batches(session: aiohttp.ClientSession):
    offset = 0
    pages_in_burst = 0
    retries = 0
    while True:
        params = {
            "active": "true",
            "closed": "false",
            "limit": str(PAGE_LIMIT),
            "offset": str(offset),
        }
        try:
            async with session.get(
                f"{GAMMA_API}/markets",
                params=params,
                headers={"User-Agent": "polymarket-scanner/1.0"},
            ) as resp:
                resp.raise_for_status()
                batch = await resp.json()
        except aiohttp.ClientResponseError as exc:
            if exc.status == 429 and retries < PAGE_MAX_RETRIES:
                retry_after = _parse_retry_after_seconds(exc.headers)
                delay = retry_after if retry_after is not None else min(
                    PAGE_RETRY_BASE_DELAY_SEC * (2 ** retries),
                    PAGE_RETRY_MAX_DELAY_SEC,
                )
                retries += 1
                logger.warning(
                    "gamma_markets_rate_limited offset=%d retry=%d delay=%.2f",
                    offset,
                    retries,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.warning(
                "gamma_markets_fetch_aborted offset=%d status=%s err=%s",
                offset,
                exc.status,
                exc,
            )
            raise GammaMarketFetchError(f"gamma_markets_fetch_aborted offset={offset} status={exc.status}") from exc
        except aiohttp.ClientError as exc:
            logger.warning("gamma_markets_fetch_failed offset=%d err=%s", offset, exc)
            raise GammaMarketFetchError(f"gamma_markets_fetch_failed offset={offset}") from exc

        retries = 0
        if not isinstance(batch, list) or not batch:
            return

        yield batch

        offset += len(batch)
        pages_in_burst += 1
        if len(batch) < PAGE_LIMIT:
            return
        await asyncio.sleep(PAGE_DELAY_SEC)
        if pages_in_burst >= PAGE_BURST_SIZE:
            await asyncio.sleep(PAGE_BURST_PAUSE_SEC)
            pages_in_burst = 0


def _maybe_collect_gc(pages_processed: int) -> None:
    if pages_processed > 0 and pages_processed % GC_COLLECT_INTERVAL_PAGES == 0:
        gc.collect()
        _trim_process_memory()


def _trim_process_memory() -> None:
    if _LIBC is None:
        return
    try:
        _LIBC.malloc_trim(0)
    except AttributeError:
        return


def filter_standalone_markets(
    raw_markets: list[dict],
    *,
    max_end_date_months: int = DEFAULT_MAX_END_DATE_MONTHS,
) -> list[dict]:
    event_counts: Counter = Counter()
    for market in raw_markets:
        slug = _get_event_slug(market)
        if slug:
            event_counts[slug] += 1
    return filter_standalone_markets_with_event_counts(
        raw_markets,
        event_counts=event_counts,
        max_end_date_months=max_end_date_months,
    )


def filter_standalone_markets_with_event_counts(
    raw_markets: list[dict],
    *,
    event_counts: Counter,
    max_end_date_months: int = DEFAULT_MAX_END_DATE_MONTHS,
) -> list[dict]:
    kept: list[dict] = []
    for market in raw_markets:
        if not _passes_candidate_filters(market, max_end_date_months=max_end_date_months):
            continue
        if not _is_standalone(market, event_counts):
            continue
        kept.append(market)
    return kept


async def fetch_candidate_markets(
    session: aiohttp.ClientSession,
    *,
    max_end_date_months: int = DEFAULT_MAX_END_DATE_MONTHS,
) -> list[StandaloneMarket]:
    markets: list[StandaloneMarket] = []
    standalone_candidates: dict[str, StandaloneMarket] = {}
    standalone_no_event: list[StandaloneMarket] = []
    event_counts: Counter = Counter()
    pages_processed = 0
    async for batch in _iter_open_market_batches(session):
        for raw_market in batch:
            event_slug = _get_event_slug(raw_market)
            if event_slug:
                event_counts[event_slug] += 1

            if not _passes_candidate_filters(raw_market, max_end_date_months=max_end_date_months):
                continue
            if raw_market.get("negRisk"):
                continue

            market = build_standalone_market(raw_market)
            if market is None:
                continue

            if not event_slug:
                standalone_no_event.append(market)
                continue

            if event_counts[event_slug] == 1:
                standalone_candidates[event_slug] = market
                continue

            standalone_candidates.pop(event_slug, None)
        pages_processed += 1
        _maybe_collect_gc(pages_processed)
        del batch
    markets.extend(standalone_no_event)
    markets.extend(standalone_candidates.values())
    markets.sort(key=lambda market: market.volume, reverse=True)
    gc.collect()
    _trim_process_memory()
    return markets
