"""Command line: refresh the results CSV in small batches (used by the scheduled GitHub Action).

    python -m src.cli refresh --max 25
    python -m src.cli analyze AAPL MSFT
    python -m src.cli usage
"""
from __future__ import annotations

import argparse
import sys

from .analysis import analyze
from .fmp import FMPClient, FMPError, RateLimitError, SymbolNotFound
from .store import load_results, load_universe, stale_symbols, upsert


def _run(client, symbols, deep, calls_reserve=12):
    rows = []
    for s in symbols:
        if client.calls_left < calls_reserve:
            print(f"Stopping: only {client.calls_left} API calls left in today's budget.")
            break
        try:
            a = analyze(client, s, deep=deep)
        except RateLimitError as e:
            print(f"Rate limit: {e}")
            break
        except SymbolNotFound as e:
            print(f"skip {s}: {e}")
            continue
        r = a.to_row()
        rows.append(r)
        print(f"{s:6s} {r['rating']:<12s} score={r['overall_score'] or 0:5.1f}  upside={(r['upside'] or 0) * 100:6.1f}%")
    if rows:
        upsert(rows)
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(prog="valuation-screener")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh", help="analyse the stalest symbols of data/universe.csv")
    r.add_argument("--max", type=int, default=25)
    r.add_argument("--max-age-days", type=int, default=7)
    r.add_argument("--deep", action="store_true", help="also fetch prices/targets/earnings (3 extra calls per symbol)")
    a = sub.add_parser("analyze", help="analyse specific tickers")
    a.add_argument("symbols", nargs="+")
    a.add_argument("--deep", action="store_true")
    sub.add_parser("usage", help="show today's API usage")
    args = p.parse_args(argv)

    try:
        client = FMPClient()
        if args.cmd == "usage":
            print(f"{client.calls_today()} calls used today, {client.calls_left} left of {client.daily_budget}.")
            return 0
        if args.cmd == "refresh":
            todo = stale_symbols(load_universe(), load_results(), args.max_age_days)[: args.max]
            print(f"Refreshing {len(todo)} symbols...")
            _run(client, todo, args.deep)
        else:
            _run(client, args.symbols, args.deep)
    except FMPError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
