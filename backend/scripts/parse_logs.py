#!/usr/bin/env python3
"""Parse Heroku JSON logs into human-readable output.

Usage:
  # Terminal (colored, columnar):
  heroku logs --app <app> -n 1500 | python scripts/parse_logs.py
  heroku logs --app <app> --tail | python scripts/parse_logs.py

  # HTML report:
  heroku logs --app <app> -n 1500 | python scripts/parse_logs.py --html > report.html

Color key (terminal):
  White/bold  = trades (buy/sell)
  Red         = errors only
  Cyan        = system events (redeemer, startup, balance)
  Dim         = heartbeat, skips
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

# ANSI
WHITE = "\033[97m"
RED = "\033[91m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

POLYMARKET_EVENT_URL = "https://polymarket.com/event"


def parse_heroku_line(raw_line: str) -> dict | None:
    idx = raw_line.find("{")
    if idx < 0:
        return None
    try:
        return json.loads(raw_line[idx:])
    except json.JSONDecodeError:
        return None


def fmt_time(ts) -> str:
    if isinstance(ts, str):
        try:
            # Handle Python logging's comma-separated ms: "2024-01-15 04:25:48,123"
            ts_clean = ts.replace(",", ".")
            dt = datetime.fromisoformat(ts_clean.replace("Z", "+00:00"))
            ms = dt.microsecond // 1000
            return f"{dt.strftime('%H:%M:%S')}.{ms:03d}"
        except ValueError:
            return ts[:12]
    elif isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts)
        ms = dt.microsecond // 1000
        return f"{dt.strftime('%H:%M:%S')}.{ms:03d}"
    return "??:??:??"


def classify_event(msg: dict) -> dict | None:
    """Parse a log message into a structured event."""
    message = msg.get("message", "")
    level = msg.get("level", "INFO")
    ts = msg.get("timestamp", "")

    if message == "trade_ledger":
        return {
            "type": "trade",
            "ts": ts,
            "epoch": msg.get("ts", 0),
            "action": msg.get("action", "?"),
            "side": msg.get("side", "?"),
            "slug": msg.get("market_slug", ""),
            "amount": msg.get("amount", 0),
            "reference_price": msg.get("reference_price"),
            "market_price": msg.get("market_price"),
            "buffered_price": msg.get("buffered_price"),
            "order_status": msg.get("order_status", ""),
            "gap": msg.get("gap", 0),
            "fair": msg.get("fair", 0),
            "spot_price": msg.get("spot_price", 0),
            "strike": msg.get("strike", 0),
            "sigma": msg.get("sigma", 0),
            "error": msg.get("error", ""),
            "interval_start": msg.get("interval_start", 0),
        }

    if message.startswith("GA LIVE"):
        evt = {"type": "strategy", "ts": ts, "text": message}
        if "ENTRY" in message:
            evt["subtype"] = "entry"
        elif "FLIP" in message:
            evt["subtype"] = "flip"
        elif "KILL" in message:
            evt["subtype"] = "kill"
        elif "skip" in message:
            evt["subtype"] = "skip"
        elif "interval done" in message:
            evt["subtype"] = "done"
            for part in message.split():
                if part.startswith("settle="):
                    evt["settle"] = part.split("=", 1)[1]
        elif "F10" in message or "F11" in message:
            evt["subtype"] = "recovery"
        elif "DANGER" in message:
            evt["subtype"] = "danger"
        elif "risk blocked" in message:
            evt["subtype"] = "risk_blocked"
        elif "recovered existing" in message:
            evt["subtype"] = "recovery"
        elif "balance recovery check failed" in message:
            evt["subtype"] = "balance_fail"
        elif "exchange timeout" in message:
            evt["subtype"] = "timeout"
        elif "BUY not confirmed" in message:
            evt["subtype"] = "buy_failed"
        # Redundant with trade_ledger rows — skip
        elif "order failed" in message:
            return None
        elif "confirmed" in message:
            return None
        elif "drawdown check failed" in message:
            return None
        elif "scan skipped" in message:
            return None
        elif "safety check failed" in message:
            return None
        else:
            evt["subtype"] = "other"
        # Extract slug
        for word in message.split():
            if "btc-updown" in word:
                evt["slug"] = word.rstrip(":")
                break
        return evt

    if message.startswith("redeemer_"):
        return {
            "type": "redeemer",
            "ts": ts,
            "action": message.replace("redeemer_", ""),
            "slug": msg.get("slug", ""),
            "size": msg.get("size"),
            "tx_hash": msg.get("tx_hash", ""),
            "gas_used": msg.get("gas_used"),
        }

    if message == "heartbeat":
        return {
            "type": "heartbeat",
            "ts": ts,
            "uptime": msg.get("uptime", "?"),
            "market": msg.get("market", "?"),
            "clob_age_ms": msg.get("clob_age_ms", -1),
            "up_ask": msg.get("up_ask", 0),
            "down_ask": msg.get("down_ask", 0),
        }

    if message == "dashboard_starting_balance":
        return {"type": "balance", "ts": ts, "balance": msg.get("balance", 0)}

    if message == "bot_starting" or message.startswith("GA LIVE started"):
        return {"type": "startup", "ts": ts, "text": message, **{
            k: msg.get(k) for k in ("bet_size", "min_signal_gap", "live_send_enabled") if msg.get(k) is not None
        }}

    if level == "ERROR" and "httpx" not in msg.get("logger", ""):
        return {"type": "error", "ts": ts, "text": message}

    return None


# ─── TERMINAL MODE ───
# Columns: TIME | TYPE | SIDE | PRICE | DETAILS

COL_TIME = 10
COL_TYPE = 14
COL_SIDE = 6
COL_PRICE = 10
# details = rest of line


def pad(s: str, width: int) -> str:
    """Pad/truncate to fixed width (ignoring ANSI codes for display)."""
    # Strip ANSI for length calc
    import re
    visible = re.sub(r"\033\[[0-9;]*m", "", s)
    if len(visible) >= width:
        return s[:width + (len(s) - len(visible))]
    return s + " " * (width - len(visible))


def format_terminal(evt: dict) -> str | None:
    t = fmt_time(evt["ts"])

    if evt["type"] == "trade":
        action = evt["action"]
        side = evt["side"]
        price_str = ""
        if evt.get("market_price"):
            price_str = f"{evt['market_price']}"
        elif evt.get("reference_price"):
            price_str = f"{evt['reference_price']:.4f}"

        details_parts = []
        if evt.get("reference_price") and evt.get("market_price"):
            details_parts.append(f"ask={evt['reference_price']:.4f}")
        if evt.get("gap"):
            details_parts.append(f"gap={evt['gap']:.3f}")
        if evt.get("fair"):
            details_parts.append(f"fair={evt['fair']:.1%}")
        if evt.get("order_status"):
            details_parts.append(f"[{evt['order_status']}]")
        if evt.get("amount"):
            details_parts.append(f"${evt['amount']:.2f}")

        details = "  ".join(details_parts)

        if action == "error":
            error_short = evt.get("error", "")[:60]
            return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                    f"{RED}{pad('ERROR', COL_TYPE)}{RESET}"
                    f"{pad(side, COL_SIDE)}"
                    f"{pad('', COL_PRICE)}"
                    f"{error_short}{RESET}")

        return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                f"{WHITE}{BOLD}{pad(action.upper(), COL_TYPE)}{RESET}"
                f"{pad(side, COL_SIDE)}"
                f"{pad(price_str, COL_PRICE)}"
                f"{details}")

    if evt["type"] == "strategy":
        sub = evt.get("subtype", "other")
        short = evt["text"].replace("GA LIVE ", "")

        if sub == "skip":
            return (f"{DIM}{pad(t, COL_TIME)}"
                    f"{pad('SKIP', COL_TYPE)}"
                    f"{short}{RESET}")
        if sub == "done":
            settle = evt.get("settle", "?")
            return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                    f"{CYAN}{pad('DONE', COL_TYPE)}{RESET}"
                    f"{pad('', COL_SIDE)}"
                    f"{pad('', COL_PRICE)}"
                    f"settle={settle}")
        if sub == "kill":
            return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                    f"{RED}{BOLD}{pad('KILL SWITCH', COL_TYPE)}{RESET}"
                    f"{short}")
        if sub == "recovery":
            return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                    f"{CYAN}{pad('RECOVERY', COL_TYPE)}{RESET}"
                    f"{short}")
        # entry/flip are redundant with trade_ledger, skip to reduce noise
        return None

    if evt["type"] == "redeemer":
        action = evt["action"].upper()
        detail_parts = []
        if evt.get("slug"):
            detail_parts.append(evt["slug"].split("-")[-1])
        if evt.get("size"):
            detail_parts.append(f"size={evt['size']}")
        if evt.get("tx_hash"):
            detail_parts.append(f"tx={evt['tx_hash'][:16]}...")
        if evt.get("gas_used"):
            detail_parts.append(f"gas={evt['gas_used']}")
        detail = "  ".join(detail_parts)
        return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                f"{CYAN}{pad('REDEEM ' + action[:6], COL_TYPE)}{RESET}"
                f"{pad('', COL_SIDE)}"
                f"{pad('', COL_PRICE)}"
                f"{detail}")

    if evt["type"] == "heartbeat":
        return (f"{DIM}{pad(t, COL_TIME)}"
                f"{pad('HEARTBEAT', COL_TYPE)}"
                f"{pad('', COL_SIDE)}"
                f"{pad('', COL_PRICE)}"
                f"{evt['uptime']}  clob={evt['clob_age_ms']}ms  "
                f"up={evt['up_ask']}  dn={evt['down_ask']}{RESET}")

    if evt["type"] == "balance":
        bal_str = f"${evt['balance']:.2f}"
        return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                f"{CYAN}{pad('BALANCE', COL_TYPE)}{RESET}"
                f"{pad('', COL_SIDE)}"
                f"{pad(bal_str, COL_PRICE)}"
                f"starting balance")

    if evt["type"] == "startup":
        return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                f"{CYAN}{BOLD}{pad('STARTUP', COL_TYPE)}{RESET}"
                f"{evt.get('text', '')}")

    if evt["type"] == "error":
        return (f"{DIM}{pad(t, COL_TIME)}{RESET}"
                f"{RED}{pad('ERROR', COL_TYPE)}{RESET}"
                f"{evt['text'][:80]}")

    return None


# ─── HTML MODE ───

def slug_to_interval_label(slug: str) -> str:
    parts = slug.rsplit("-", 1)
    try:
        start = int(parts[-1])
        t0 = datetime.fromtimestamp(start, tz=timezone.utc)
        t1 = datetime.fromtimestamp(start + 300, tz=timezone.utc)
        return f"{t0.strftime('%H:%M:%S')} - {t1.strftime('%H:%M:%S UTC')}"
    except (ValueError, IndexError):
        return slug


def events_to_html(events: list[dict]) -> str:
    markets: dict[str, list[dict]] = defaultdict(list)
    ungrouped: list[dict] = []

    for evt in events:
        slug = evt.get("slug")
        if not slug and evt["type"] == "trade":
            slug = evt.get("slug")
        if not slug and evt["type"] == "strategy":
            for word in evt.get("text", "").split():
                if "btc-updown" in word:
                    slug = word.rstrip(":")
                    break
        if not slug and evt["type"] == "redeemer":
            slug = evt.get("slug")
        if slug:
            markets[slug].append(evt)
        else:
            ungrouped.append(evt)

    def slug_sort_key(s):
        try:
            return int(s.rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            return 0

    sorted_slugs = sorted(markets.keys(), key=slug_sort_key)

    html = [HTML_HEAD]

    # Summary
    total_buys = sum(1 for e in events if e["type"] == "trade" and e["action"] == "buy")
    total_errors = sum(1 for e in events if e["type"] == "trade" and e["action"] == "error")
    total_redeems = sum(1 for e in events if e["type"] == "redeemer" and "success" in e.get("action", ""))
    balance_evts = [e for e in events if e["type"] == "balance"]
    starting_bal = balance_evts[0]["balance"] if balance_evts else None

    html.append('<div class="summary">')
    html.append(f'<span>Intervals: <b>{len(sorted_slugs)}</b></span>')
    html.append(f'<span>Trades: <b>{total_buys}</b></span>')
    html.append(f'<span>Errors: <b>{total_errors}</b></span>')
    html.append(f'<span>Redeemed: <b>{total_redeems}</b></span>')
    if starting_bal is not None:
        html.append(f'<span>Starting Balance: <b>${starting_bal:.2f}</b></span>')
    html.append('</div>')

    col_header = ('<div class="col-header">'
                   '<span class="ch-time">Time</span>'
                   '<span class="ch-type">Type</span>'
                   '<span class="ch-side">Side</span>'
                   '<span class="ch-price">Price</span>'
                   '<span class="ch-details">Details</span>'
                   '</div>')

    # Ungrouped
    startup_evts = [e for e in ungrouped if e["type"] in ("startup", "balance")]
    if startup_evts:
        html.append('<div class="market-section">')
        html.append('<div class="market-header"><h2>Startup</h2></div>')
        html.append(col_header)
        for evt in startup_evts:
            html.append(render_row_html(evt))
        html.append('</div>')

    # Each market
    for slug in sorted_slugs:
        evts = markets[slug]
        label = slug_to_interval_label(slug)
        link = f"{POLYMARKET_EVENT_URL}/{slug}"

        # Outcome
        outcome_html = ""
        for evt in evts:
            if evt["type"] == "redeemer" and "success" in evt.get("action", ""):
                outcome_html = '<span class="badge badge-win">WON</span>'
            if evt["type"] == "strategy" and evt.get("subtype") == "done":
                settle = evt.get("settle", "")
                if settle.startswith("settled") and not outcome_html:
                    outcome_html = '<span class="badge badge-settled">SETTLED</span>'

        # Quick stats
        buys = [e for e in evts if e["type"] == "trade" and e["action"] == "buy"]
        errors = [e for e in evts if e["type"] == "trade" and e["action"] == "error"]

        html.append('<div class="market-section">')
        html.append(f'<div class="market-header">')
        html.append(f'<a href="{link}" target="_blank">{slug}</a>')
        html.append(f'<span class="interval-time">{label}</span>')
        html.append(outcome_html)
        if errors:
            html.append(f'<span class="badge badge-error">{len(errors)} error{"s" if len(errors)>1 else ""}</span>')
        html.append('</div>')

        if buys:
            b = buys[0]
            html.append('<div class="quick-stats">')
            html.append(f'<span>Side: <b>{b["side"]}</b></span>')
            html.append(f'<span>Amount: <b>${b["amount"]:.2f}</b></span>')
            if b.get("market_price"):
                html.append(f'<span>Fill: <b>{b["market_price"]}</b></span>')
            elif b.get("reference_price"):
                html.append(f'<span>Ask: <b>{b["reference_price"]:.4f}</b></span>')
            if b.get("gap"):
                html.append(f'<span>Gap: <b>{b["gap"]:.3f}</b></span>')
            if b.get("fair"):
                html.append(f'<span>Fair: <b>{b["fair"]:.1%}</b></span>')
            if b.get("spot_price"):
                html.append(f'<span>Spot: <b>${b["spot_price"]:,.2f}</b></span>')
            if b.get("strike"):
                html.append(f'<span>Strike: <b>${b["strike"]:,.2f}</b></span>')
            html.append('</div>')

        html.append(col_header)
        for evt in evts:
            html.append(render_row_html(evt))

        html.append('</div>')

    html.append('</div></body></html>')
    return "\n".join(html)


def _clean_error(raw: str) -> str:
    """Shorten common PolyApiException messages."""
    import re
    m = re.search(r"error_message=\{.*?'error':\s*'([^']+)'\}", raw)
    if m:
        msg = m.group(1)
        if "FAK" in msg:
            return "no FAK match"
        if "balance" in msg or "allowance" in msg:
            return "insufficient balance"
        return msg
    if raw.startswith("flip_sell: "):
        return "flip sell failed: " + _clean_error(raw[11:])
    if raw.startswith("flip_balance_check: "):
        return "flip balance check failed"
    if "Request exception" in raw:
        return "request failed (no response)"
    m = re.search(r"error_message=(.+?)[\]\)]*$", raw)
    if m:
        return m.group(1).strip()
    if "PolyApiException" in raw:
        return raw.split("PolyApiException")[-1].strip("[] ")
    return raw


def render_row_html(evt: dict) -> str:
    t = fmt_time(evt["ts"])

    if evt["type"] == "trade":
        action = evt["action"]
        side = evt["side"]
        cls = ("error" if action in ("error", "kill_switch")
               else "dim" if action == "attempt"
               else "system" if action in ("recovery", "risk_blocked")
               else "trade")
        price = ""
        if evt.get("market_price"):
            price = str(evt["market_price"])
        elif evt.get("reference_price"):
            price = f'{evt["reference_price"]:.4f}'

        details = []
        if evt.get("reference_price"):
            details.append(f'ask={evt["reference_price"]:.4f}')
        if evt.get("gap"):
            details.append(f'gap={evt["gap"]:.3f}')
        if evt.get("fair"):
            details.append(f'fair={evt["fair"]:.1%}')
        if evt.get("order_status"):
            details.append(f'[{evt["order_status"]}]')
        if evt.get("amount"):
            details.append(f'${evt["amount"]:.2f}')
        if evt.get("error"):
            details.append(_clean_error(evt["error"]))

        return (f'<div class="row row-{cls}">'
                f'<span class="c-time">{t}</span>'
                f'<span class="c-type">{action.upper()}</span>'
                f'<span class="c-side">{side}</span>'
                f'<span class="c-price">{price}</span>'
                f'<span class="c-details">{" &middot; ".join(details)}</span>'
                f'</div>')

    if evt["type"] == "strategy":
        sub = evt.get("subtype", "other")
        # Skip entry/flip (redundant with trade_ledger rows)
        if sub == "entry":
            return ""
        label = {
            "done": "DONE", "skip": "SKIP", "kill": "KILL SWITCH",
            "recovery": "RECOVERY", "flip": "FLIP", "danger": "DANGER",
            "risk_blocked": "RISK BLOCKED", "balance_fail": "BAL FAIL",
            "timeout": "TIMEOUT", "buy_failed": "BUY FAILED",
        }.get(sub, sub.upper())
        detail = ""
        if sub == "done":
            detail = f'settle={evt.get("settle", "?")}'
        elif sub == "skip":
            detail = evt["text"].replace("GA LIVE ", "")
        elif sub == "flip":
            detail = evt["text"].replace("GA LIVE FLIP ", "").replace("GA LIVE ", "")
        else:
            detail = evt["text"].replace("GA LIVE ", "")
        cls = ("dim" if sub in ("skip", "done")
               else "error" if sub in ("kill", "danger", "balance_fail", "timeout", "buy_failed")
               else "system" if sub in ("recovery", "risk_blocked")
               else "")
        return (f'<div class="row row-{cls}">'
                f'<span class="c-time">{t}</span>'
                f'<span class="c-type">{label}</span>'
                f'<span class="c-side"></span>'
                f'<span class="c-price"></span>'
                f'<span class="c-details">{detail}</span>'
                f'</div>')

    if evt["type"] == "redeemer":
        action = evt["action"]
        details = []
        if evt.get("size"):
            details.append(f'size={evt["size"]}')
        if evt.get("tx_hash"):
            details.append(f'tx={evt["tx_hash"][:20]}...')
        if evt.get("gas_used"):
            details.append(f'gas={evt["gas_used"]}')
        label = "REDEEM" if "redeem" in action else action.upper()
        return (f'<div class="row row-system">'
                f'<span class="c-time">{t}</span>'
                f'<span class="c-type">{label}</span>'
                f'<span class="c-side"></span>'
                f'<span class="c-price"></span>'
                f'<span class="c-details">{" &middot; ".join(details)}</span>'
                f'</div>')

    if evt["type"] == "heartbeat":
        return (f'<div class="row row-dim">'
                f'<span class="c-time">{t}</span>'
                f'<span class="c-type">HEARTBEAT</span>'
                f'<span class="c-side"></span>'
                f'<span class="c-price"></span>'
                f'<span class="c-details">{evt["uptime"]} &middot; clob={evt["clob_age_ms"]}ms &middot; up={evt["up_ask"]} &middot; dn={evt["down_ask"]}</span>'
                f'</div>')

    if evt["type"] == "balance":
        return (f'<div class="row row-system">'
                f'<span class="c-time">{t}</span>'
                f'<span class="c-type">BALANCE</span>'
                f'<span class="c-side"></span>'
                f'<span class="c-price">${evt["balance"]:.2f}</span>'
                f'<span class="c-details">session starting balance</span>'
                f'</div>')

    if evt["type"] == "startup":
        return (f'<div class="row row-system">'
                f'<span class="c-time">{t}</span>'
                f'<span class="c-type">STARTUP</span>'
                f'<span class="c-side"></span>'
                f'<span class="c-price"></span>'
                f'<span class="c-details">{evt.get("text", "")}</span>'
                f'</div>')

    if evt["type"] == "error":
        return (f'<div class="row row-error">'
                f'<span class="c-time">{t}</span>'
                f'<span class="c-type">ERROR</span>'
                f'<span class="c-side"></span>'
                f'<span class="c-price"></span>'
                f'<span class="c-details">{evt["text"][:120]}</span>'
                f'</div>')

    return ""


HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GA Champion Trade Log</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "SFMono-Regular", ui-monospace, monospace;
  background: #0a0a0a; color: #ccc;
  padding: 1rem; max-width: 1200px; margin: 0 auto;
  font-size: 13px;
}
h1 { font-size: 1.2rem; margin-bottom: 0.75rem; color: #f0f0f0; font-family: system-ui, sans-serif; }
.summary {
  display: flex; flex-wrap: wrap; gap: 1.5rem;
  padding: 0.6rem 1rem; margin-bottom: 0.75rem;
  background: #151515; border: 1px solid #2a2a2a; border-radius: 6px;
  font-family: system-ui, sans-serif; font-size: 0.85rem;
}
.summary b { color: #fff; }

/* Column header */
.col-header {
  display: flex; gap: 0; padding: 0.3rem 1rem;
  color: #666; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
  border-bottom: 1px solid #222;
}
.ch-time { min-width: 95px; }
.ch-type { min-width: 110px; }
.ch-side { min-width: 50px; }
.ch-price { min-width: 70px; }
.ch-details { flex: 1; }

/* Market sections */
.market-section {
  margin-bottom: 1rem;
  border: 1px solid #2a2a2a; border-radius: 6px;
  background: #111; overflow: hidden;
}
.market-header {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem;
  padding: 0.5rem 1rem;
  background: #1a1a1a; border-bottom: 1px solid #2a2a2a;
  font-family: system-ui, sans-serif; font-size: 0.85rem;
}
.market-header a { color: #6ba3ff; text-decoration: none; font-weight: 600; }
.market-header a:hover { text-decoration: underline; }
.interval-time { font-size: 0.75rem; color: #888; font-family: monospace; }
.badge {
  font-size: 10px; font-weight: 700; padding: 2px 8px;
  border-radius: 3px; text-transform: uppercase; letter-spacing: 0.05em;
}
.badge-win { background: #0a3d0a; color: #4ade80; }
.badge-settled { background: #1a2a1a; color: #86efac; }
.badge-pending { background: #3d2a0a; color: #fbbf24; }
.badge-error { background: #3d0a0a; color: #f87171; }
.quick-stats {
  display: flex; flex-wrap: wrap; gap: 1rem;
  padding: 0.4rem 1rem; font-size: 12px;
  border-bottom: 1px solid #1f1f1f;
  font-family: system-ui, sans-serif;
}
.quick-stats b { color: #fff; }

/* Event rows — columnar */
.row {
  display: flex; align-items: baseline;
  padding: 3px 1rem;
  border-bottom: 1px solid #161616;
}
.row:last-child { border-bottom: none; }
.c-time { min-width: 95px; color: #666; }
.c-type { min-width: 110px; font-weight: 600; }
.c-side { min-width: 50px; }
.c-price { min-width: 70px; }
.c-details { flex: 1; color: #999; }

/* Row variants */
.row-trade .c-type { color: #e0e0e0; }
.row-error { background: #7f1d1d; color: #fff; }
.row-error .c-type { color: #fff; }
.row-error .c-time { color: #fca5a5; }
.row-error .c-details { color: #fff; }
.row-system .c-type { color: #67e8f9; }
.row-dim { color: #555; }
.row-dim .c-type { color: #555; font-weight: 400; }
.row-dim .c-details { color: #444; }
</style>
</head>
<body>
<h1>GA Champion Trade Log</h1>
<div>"""


def load_events_from_db(database_url: str, limit: int = 5000) -> list[dict]:
    """Load trade events from Postgres and convert to classified events."""
    import sqlalchemy as sa
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    engine = sa.create_engine(database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT * FROM trade_events ORDER BY ts ASC LIMIT :limit"),
            {"limit": limit},
        ).mappings().all()

    events = []
    for row in rows:
        # Convert DB row to the same format as classify_event output for trades
        d = dict(row)
        d["type"] = "trade"
        d["action"] = d.get("action", "")
        d["side"] = d.get("side", "")
        # Use epoch ts for fmt_time
        d["ts"] = d.get("ts", 0)
        d["slug"] = d.get("market_slug", "")
        events.append(d)
    return events


def main():
    html_mode = "--html" in sys.argv
    db_mode = "--db" in sys.argv
    events: list[dict] = []
    header_printed = False

    if db_mode:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            print("ERROR: DATABASE_URL not set", file=sys.stderr)
            sys.exit(1)
        events = load_events_from_db(database_url)
        if html_mode:
            print(events_to_html(events))
        else:
            for evt in events:
                formatted = format_terminal(evt)
                if formatted:
                    print(formatted)
        return

    for raw_line in sys.stdin:
        raw_line = raw_line.rstrip()
        if not raw_line:
            continue
        msg = parse_heroku_line(raw_line)
        if msg is None:
            if not html_mode and ("Error" in raw_line or "crashed" in raw_line):
                print(f"{DIM}{raw_line}{RESET}")
            continue
        evt = classify_event(msg)
        if evt is None:
            continue
        if html_mode:
            events.append(evt)
        else:
            if not header_printed:
                header = (f"{DIM}{pad('TIME', COL_TIME)}"
                          f"{pad('TYPE', COL_TYPE)}"
                          f"{pad('SIDE', COL_SIDE)}"
                          f"{pad('PRICE', COL_PRICE)}"
                          f"DETAILS{RESET}")
                print(header)
                print(f"{DIM}{'─' * 90}{RESET}")
                header_printed = True
            formatted = format_terminal(evt)
            if formatted:
                print(formatted)
                sys.stdout.flush()

    if html_mode:
        print(events_to_html(events))


if __name__ == "__main__":
    main()
