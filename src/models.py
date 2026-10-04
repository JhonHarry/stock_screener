"""Raw company data container + loader."""
from __future__ import annotations

from dataclasses import dataclass, field

from .fmp import SymbolNotFound
from .utils import parse_date, pick, safe_div


@dataclass
class CompanyData:
    symbol: str
    profile: dict = field(default_factory=dict)
    ratios: dict = field(default_factory=dict)
    key_metrics: dict = field(default_factory=dict)
    income: list = field(default_factory=list)      # newest first
    cashflow: list = field(default_factory=list)    # newest first
    dividends: list = field(default_factory=list)
    estimates: list = field(default_factory=list)
    price_target: dict = field(default_factory=dict)
    prices: list = field(default_factory=list)      # oldest first
    earnings: list = field(default_factory=list)

    @property
    def price(self):
        return pick(self.profile, "price")

    @property
    def market_cap(self):
        return pick(self.profile, "marketCap", "mktCap")

    @property
    def beta(self):
        return pick(self.profile, "beta")

    @property
    def shares(self):
        return safe_div(self.market_cap, self.price)

    @property
    def name(self):
        return self.profile.get("companyName") or self.symbol

    @property
    def sector(self):
        return self.profile.get("sector") or "—"

    @property
    def industry(self):
        return self.profile.get("industry") or "—"


def _newest_first(rows):
    return sorted(rows or [], key=lambda r: str(r.get("date", "")), reverse=True)


def load_company(client, symbol, deep=True):
    """Fetch everything needed to analyse ``symbol``.

    Lean mode (screener) uses ~6-7 API calls; deep mode adds price history,
    price targets and earnings history (~3 more).
    """
    symbol = symbol.upper().strip()
    profile = client.profile(symbol)
    if not profile or pick(profile, "price") is None:
        raise SymbolNotFound(f"No data for '{symbol}' (not a US ticker, or not available on your FMP plan).")

    c = CompanyData(symbol=symbol, profile=profile)
    c.ratios = client.ratios_ttm(symbol)
    c.key_metrics = client.key_metrics_ttm(symbol)
    c.income = _newest_first(client.income(symbol))
    c.cashflow = _newest_first(client.cashflow(symbol))
    c.estimates = sorted(client.estimates(symbol), key=lambda r: str(r.get("date", "")))
    if (pick(profile, "lastDividend") or 0) > 0:
        c.dividends = client.dividends(symbol)
    if deep:
        c.price_target = client.price_target(symbol)
        c.prices = sorted(client.prices(symbol), key=lambda r: str(r.get("date", "")))
        c.earnings = client.earnings(symbol)
    return c
