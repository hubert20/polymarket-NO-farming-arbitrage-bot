"""Query trade_events DB for latency and performance stats."""
import os
import sys
import time

import sqlalchemy as sa

def main():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL not set")
        sys.exit(1)
    db_url = db_url.replace("postgres://", "postgresql://")
    engine = sa.create_engine(db_url)
    cutoff = time.time() - 7200  # last 2 hours

    with engine.connect() as conn:
        # Event summary
        rows = conn.execute(sa.text(
            "SELECT action, count(*), round(avg(amount)::numeric, 4), "
            "min(to_timestamp(ts))::text, max(to_timestamp(ts))::text "
            "FROM trade_events WHERE ts > :cutoff "
            "GROUP BY action ORDER BY count(*) DESC"
        ), {"cutoff": cutoff}).all()
        print("=== EVENT SUMMARY (last 2h) ===")
        for r in rows:
            print(f"  {r[0]:25s} count={r[1]:4d}  avg_amt={str(r[2]):>10s}  last={str(r[4])[:19]}")

        # Buy fills
        buy_rows = conn.execute(sa.text(
            "SELECT to_timestamp(ts)::text, side, reference_price, amount, "
            "extra::json->>'fill_price' as fill_price, "
            "extra::json->>'filled_shares' as filled_shares, "
            "extra::json->>'market_price' as market_price "
            "FROM trade_events WHERE ts > :cutoff AND action = 'buy' ORDER BY ts"
        ), {"cutoff": cutoff}).all()
        print("\n=== BUY FILLS ===")
        for r in buy_rows:
            ref = float(r[2]) if r[2] else 0
            fp = float(r[4]) if r[4] else 0
            shares = float(r[5]) if r[5] else 0
            slip = fp - ref if fp and ref else 0
            print(f"  {str(r[0])[:19]}  {r[1]:4s}  ref={ref:.2f}  fill={fp:.4f}  shares={shares:.2f}  spent=${float(r[3]):.2f}  slip={slip:+.4f}")

        # Settlements
        done_rows = conn.execute(sa.text(
            "SELECT to_timestamp(ts)::text, side, amount, "
            "extra::json->>'settle_status' as settle_status, "
            "extra::json->>'entry_spent_usd' as entry_spent "
            "FROM trade_events WHERE ts > :cutoff AND action = 'done' ORDER BY ts"
        ), {"cutoff": cutoff}).all()
        print("\n=== SETTLEMENTS ===")
        total_pnl = 0.0
        wins = 0
        losses = 0
        for r in done_rows:
            pnl = float(r[2] or 0)
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            else:
                losses += 1
            entry = r[4] or "?"
            print(f"  {str(r[0])[:19]}  {r[1]:4s}  pnl=${pnl:+.4f}  {r[3]}  entry=${entry}")
        print(f"  TOTAL: {wins}W {losses}L  PnL=${total_pnl:+.4f}")

        # Errors
        err_rows = conn.execute(sa.text(
            "SELECT to_timestamp(ts)::text, action, side, error "
            "FROM trade_events WHERE ts > :cutoff AND error IS NOT NULL AND error != '' "
            "ORDER BY ts"
        ), {"cutoff": cutoff}).all()
        print(f"\n=== ERRORS ({len(err_rows)} total) ===")
        for r in err_rows:
            err_short = str(r[3])[:80] if r[3] else ""
            print(f"  {str(r[0])[:19]}  {r[1]:25s}  {r[2]:4s}  {err_short}")

        # Interval timing: time from interval start to buy
        timing_rows = conn.execute(sa.text(
            "SELECT b.interval_start, "
            "b.ts - b.interval_start as secs_to_buy, "
            "b.side, b.reference_price, "
            "b.extra::json->>'fill_price' as fill_price "
            "FROM trade_events b "
            "WHERE b.ts > :cutoff AND b.action = 'buy' "
            "ORDER BY b.ts"
        ), {"cutoff": cutoff}).all()
        print("\n=== ENTRY LATENCY (seconds from interval start to fill) ===")
        latencies = []
        for r in timing_rows:
            lat = float(r[1])
            latencies.append(lat)
            print(f"  interval={r[0]}  {r[2]:4s}  entry_at={lat:.1f}s  ref={float(r[3]):.2f}  fill={r[4]}")
        if latencies:
            print(f"  AVG={sum(latencies)/len(latencies):.1f}s  MIN={min(latencies):.1f}s  MAX={max(latencies):.1f}s")


if __name__ == "__main__":
    main()
