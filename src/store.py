"""Flat CSV store of screener results (committed to git so updates are tracked)."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_PATH = DATA_DIR / "results.csv"
UNIVERSE_PATH = DATA_DIR / "universe.csv"


def _results_path(path=None) -> Path:
    return Path(path or os.getenv("VS_RESULTS_PATH") or RESULTS_PATH)


def load_results(path=None) -> pd.DataFrame:
    path = _results_path(path)
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path)
    return pd.DataFrame()


def upsert(rows, path=None) -> pd.DataFrame:
    """Insert/replace rows (list of dicts) keyed by symbol and save."""
    path = _results_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame(rows)
    if new.empty:
        return load_results(path)
    old = load_results(path)
    df = new if old.empty else pd.concat([old[~old["symbol"].isin(new["symbol"])], new], ignore_index=True)
    df = df.sort_values("symbol").reset_index(drop=True)
    df.to_csv(path, index=False)
    return df


def load_universe(path=UNIVERSE_PATH) -> list[str]:
    path = Path(path)
    if not path.exists():
        return []
    return [s.strip().upper() for s in pd.read_csv(path)["symbol"].dropna()]


def stale_symbols(universe, results: pd.DataFrame, max_age_days=7) -> list[str]:
    """Universe symbols never analysed first, then oldest-updated first."""
    if results.empty:
        return list(universe)
    upd = pd.to_datetime(results.set_index("symbol")["updated"], errors="coerce")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=max_age_days)
    never = [s for s in universe if s not in upd.index]
    old = [s for s in upd[upd < cutoff].sort_values().index if s in set(universe)]
    return never + old
