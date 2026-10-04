"""Financial Modeling Prep client with a persistent SQLite cache.

The free FMP plan allows ~250 calls/day, so every response is cached on disk
(with a per-endpoint TTL) and a daily call counter stops us before the quota.
Endpoints that the plan does not include (HTTP 402/403) are cached as ``None``
so we never waste calls retrying them.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

import requests

try:  # optional: read FMP_API_KEY from a local .env file
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_URL = "https://financialmodelingprep.com/stable"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "cache.sqlite"
DEFAULT_DAILY_BUDGET = 240  # free plan = 250; keep a small safety margin

_MISS = object()


class FMPError(Exception):
    pass


class MissingKeyError(FMPError):
    pass


class RateLimitError(FMPError):
    pass


class SymbolNotFound(FMPError):
    pass


class FMPClient:
    def __init__(self, api_key=None, db_path=None, daily_budget=None, session=None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.db_path = Path(db_path or os.getenv("VS_CACHE_DB") or DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_budget = int(daily_budget or os.getenv("FMP_DAILY_BUDGET") or DEFAULT_DAILY_BUDGET)
        self.session = session or requests.Session()
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, ts REAL, payload TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, calls INTEGER)")

    # ------------------------------------------------------------------ storage
    def _conn(self):
        return sqlite3.connect(self.db_path, timeout=30)

    def _cache_get(self, key, ttl_hours):
        with self._conn() as c:
            row = c.execute("SELECT ts, payload FROM cache WHERE key=?", (key,)).fetchone()
        if not row:
            return _MISS
        ts, payload = row
        if time.time() - ts > ttl_hours * 3600:
            return _MISS
        return json.loads(payload)

    def _cache_put(self, key, data):
        with self._conn() as c:
            c.execute("REPLACE INTO cache(key, ts, payload) VALUES (?,?,?)", (key, time.time(), json.dumps(data)))

    def calls_today(self):
        with self._conn() as c:
            row = c.execute("SELECT calls FROM usage WHERE day=?", (date.today().isoformat(),)).fetchone()
        return row[0] if row else 0

    def _bump(self):
        day = date.today().isoformat()
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO usage(day, calls) VALUES (?, 0)", (day,))
            c.execute("UPDATE usage SET calls = calls + 1 WHERE day=?", (day,))

    @property
    def calls_left(self):
        return max(0, self.daily_budget - self.calls_today())

    # --------------------------------------------------------------------- http
    def get(self, endpoint, ttl_hours=24, **params):
        """GET ``/stable/<endpoint>``; returns parsed JSON or None if unavailable."""
        key = endpoint + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        hit = self._cache_get(key, ttl_hours)
        if hit is not _MISS:
            return hit
        if not self.api_key:
            raise MissingKeyError("No FMP API key configured (set FMP_API_KEY or paste it in the sidebar).")
        if self.calls_today() >= self.daily_budget:
            raise RateLimitError(f"Daily call budget reached ({self.daily_budget}). Cached data still works.")

        resp = self.session.get(f"{BASE_URL}/{endpoint}", params={**params, "apikey": self.api_key}, timeout=25)
        self._bump()
        if resp.status_code == 401:
            raise FMPError("FMP rejected the API key (401). Check that it is correct.")
        if resp.status_code == 429:
            raise RateLimitError("FMP rate limit hit (429). Try again later.")
        if resp.status_code in (402, 403, 404):
            # not part of the plan / unknown symbol: remember so we don't retry for a week
            self._cache_put(key, None)
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and ("Error Message" in data or "error" in data):
            msg = str(data.get("Error Message") or data.get("error"))
            if "limit" in msg.lower() and "reach" in msg.lower():
                raise RateLimitError(msg)
            if "api key" in msg.lower() and ("invalid" in msg.lower() or "missing" in msg.lower()):
                raise FMPError(msg)
            self._cache_put(key, None)
            return None
        self._cache_put(key, data)
        return data

    def get_list(self, endpoint, ttl_hours=24, **params):
        data = self.get(endpoint, ttl_hours, **params)
        if isinstance(data, list):
            return data
        return [data] if isinstance(data, dict) and data else []

    def get_one(self, endpoint, ttl_hours=24, **params):
        rows = self.get_list(endpoint, ttl_hours, **params)
        return rows[0] if rows else {}

    # ------------------------------------------------------------ typed helpers
    def profile(self, s):
        return self.get_one("profile", 168, symbol=s)

    def ratios_ttm(self, s):
        return self.get_one("ratios-ttm", 24, symbol=s)

    def key_metrics_ttm(self, s):
        return self.get_one("key-metrics-ttm", 24, symbol=s)

    def income(self, s, limit=5):
        return self.get_list("income-statement", 168, symbol=s, period="annual", limit=limit)

    def cashflow(self, s, limit=5):
        return self.get_list("cash-flow-statement", 168, symbol=s, period="annual", limit=limit)

    def dividends(self, s):
        return self.get_list("dividends", 168, symbol=s)

    def estimates(self, s, limit=6):
        return self.get_list("analyst-estimates", 72, symbol=s, period="annual", page=0, limit=limit)

    def price_target(self, s):
        return self.get_one("price-target-consensus", 72, symbol=s)

    def earnings(self, s):
        return self.get_list("earnings", 72, symbol=s, limit=16)

    def prices(self, s, days=400):
        frm = (date.today() - timedelta(days=days)).isoformat()
        return self.get_list("historical-price-eod/light", 24, symbol=s, **{"from": frm})

    def screener(self, **filters):
        return self.get_list("company-screener", 24, **filters)
