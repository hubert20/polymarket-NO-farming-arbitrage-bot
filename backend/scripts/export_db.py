#!/usr/bin/env python3
"""Export all trade_events from Heroku Postgres to CSV.

Usage:
    python scripts/export_db.py                  # exports to trade_events_export.csv
    python scripts/export_db.py -o my_dump.csv   # custom output path

Requires `DATABASE_URL`, or fetches it from Heroku when `--app` or
`HEROKU_APP_NAME` is set.
"""

import argparse
import csv
import os
import subprocess
import sys

import sqlalchemy as sa


def get_database_url(app_name: str | None) -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    if not app_name:
        print(
            "ERROR: DATABASE_URL not set. Provide --app, set HEROKU_APP_NAME, "
            "or export DATABASE_URL directly.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        result = subprocess.run(
            ["heroku", "config:get", "DATABASE_URL", "-a", app_name],
            capture_output=True, text=True, check=True,
        )
        url = result.stdout.strip()
        if url:
            return url
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    print(f"ERROR: DATABASE_URL not set and could not fetch from Heroku app '{app_name}'", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Export trade_events to CSV")
    parser.add_argument("-o", "--output", default="trade_events_export.csv")
    parser.add_argument("--app", default=os.environ.get("HEROKU_APP_NAME"))
    parser.add_argument("--table", default="trade_events",
                        choices=["trade_events", "orders", "fills", "positions", "bot_state", "all"])
    args = parser.parse_args()

    db_url = get_database_url(args.app)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = sa.create_engine(db_url, pool_pre_ping=True)
    meta = sa.MetaData()
    meta.reflect(bind=engine)

    tables = list(meta.tables.keys()) if args.table == "all" else [args.table]

    for table_name in tables:
        if table_name not in meta.tables:
            print(f"Table '{table_name}' not found, skipping", file=sys.stderr)
            continue

        table = meta.tables[table_name]
        out_path = args.output if len(tables) == 1 else f"{table_name}_export.csv"

        with engine.connect() as conn:
            rows = conn.execute(sa.select(table).order_by(sa.text("1"))).fetchall()
            columns = list(table.columns.keys())

        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

        print(f"{table_name}: {len(rows)} rows → {out_path}")


if __name__ == "__main__":
    main()
