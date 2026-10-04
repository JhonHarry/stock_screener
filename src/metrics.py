"""Turn raw FMP payloads into a flat dict of analyst-style metrics."""
from __future__ import annotations

from datetime import date, timedelta

from .models import CompanyData
from .utils import cagr, num, parse_date, pick, safe_div


def _pos(x):
    """Multiples that are zero/negative are meaningless -> None."""
    return x if x is not None and x > 0 else None


def _series(rows, *keys):
    return [pick(r, *keys) for r in rows]


def _period_cagr(values, years):
    """CAGR over ``years`` using newest-first ``values``; falls back to the longest span available."""
    vals = [v for v in values]
    if len(vals) < 2:
        return None
    n = min(years, len(vals) - 1)
    return cagr(vals[0], vals[n], n)


def _price_return(prices, days):
    if not prices:
        return None
    last = prices[-1]
    last_d = parse_date(last.get("date"))
    last_p = pick(last, "price", "close")
    if last_d is None or last_p is None:
        return None
    target = last_d - timedelta(days=days)
    for row in reversed(prices):
        d = parse_date(row.get("date"))
        if d and d <= target:
            base = pick(row, "price", "close")
            return safe_div(last_p, base) - 1 if base else None
    return None


def future_estimates(c: CompanyData, today=None):
    today = today or date.today()
    out = [e for e in c.estimates if (parse_date(e.get("date")) or date.min) > today]
    return sorted(out, key=lambda e: str(e.get("date")))


def compute_metrics(c: CompanyData, today=None) -> dict:
    today = today or date.today()
    r, k, inc, cf = c.ratios, c.key_metrics, c.income, c.cashflow
    price, mcap = c.price, c.market_cap
    m: dict = {"price": price, "market_cap": mcap, "beta": c.beta}

    # ---------------------------------------------------------------- earnings
    eps_fy = pick(inc[0], "epsDiluted", "eps") if inc else None
    pe_raw = pick(r, "priceToEarningsRatioTTM", "peRatioTTM")
    if pe_raw is None and price and eps_fy and eps_fy > 0:
        pe_raw = price / eps_fy
    eps_ttm = safe_div(price, pe_raw) if (pe_raw and pe_raw > 0) else eps_fy
    m["eps_ttm"] = eps_ttm
    m["pe"] = _pos(pe_raw)
    m["earnings_yield"] = safe_div(eps_ttm, price)

    fut = future_estimates(c, today)
    nxt = fut[0] if fut else {}
    m["fwd_eps"] = pick(nxt, "epsAvg")
    m["fwd_revenue"] = pick(nxt, "revenueAvg")
    m["fwd_pe"] = _pos(safe_div(price, m["fwd_eps"])) if (m["fwd_eps"] or 0) > 0 else None
    m["eps_expansion"] = (m["pe"] / m["fwd_pe"] - 1) if (m["pe"] and m["fwd_pe"]) else None

    # ------------------------------------------------------------------ growth
    rev = _series(inc, "revenue")
    eps = _series(inc, "epsDiluted", "eps")
    fcf = _series(cf, "freeCashFlow")
    m["rev_cagr_3y"] = _period_cagr(rev, 3)
    m["eps_cagr_3y"] = _period_cagr(eps, 3)
    m["fcf_cagr_3y"] = _period_cagr(fcf, 3)
    m["rev_growth_yoy"] = (rev[0] / rev[1] - 1) if len(rev) > 1 and rev[0] and rev[1] and rev[1] > 0 else None

    m["fwd_rev_growth"] = None
    m["fwd_eps_growth"] = None
    fy0 = parse_date(inc[0].get("date")) if inc else None
    if fy0 and fut:
        if rev and rev[0] and rev[0] > 0 and m["fwd_revenue"]:
            gap = max(1, (parse_date(nxt.get("date")) or today).year - fy0.year)
            m["fwd_rev_growth"] = cagr(m["fwd_revenue"], rev[0], gap)
        if eps_fy and eps_fy > 0:
            best = None
            for e in fut:
                ed = parse_date(e.get("date"))
                ev = pick(e, "epsAvg")
                if ed and ev and ev > 0 and 1 <= ed.year - fy0.year <= 3:
                    best = (ed.year - fy0.year, ev)
            if best:
                m["fwd_eps_growth"] = cagr(best[1], eps_fy, best[0])

    g_pct = (m["fwd_eps_growth"] * 100) if m["fwd_eps_growth"] is not None else None
    peg = safe_div(m["fwd_pe"], g_pct) if g_pct and g_pct > 0 else pick(r, "priceToEarningsGrowthRatioTTM", "pegRatioTTM")
    m["peg"] = _pos(peg)

    # ----------------------------------------------------------- profitability
    rev0 = rev[0] if rev else None
    m["gross_margin"] = pick(r, "grossProfitMarginTTM") or safe_div(pick(inc[0], "grossProfit") if inc else None, rev0)
    m["op_margin"] = pick(r, "operatingProfitMarginTTM") or safe_div(pick(inc[0], "operatingIncome") if inc else None, rev0)
    m["net_margin"] = pick(r, "netProfitMarginTTM") or safe_div(pick(inc[0], "netIncome") if inc else None, rev0)
    m["roe"] = pick(k, "returnOnEquityTTM", "roeTTM")
    m["roic"] = pick(k, "returnOnInvestedCapitalTTM", "roicTTM")
    m["roa"] = pick(k, "returnOnAssetsTTM", "roaTTM")
    fcf0 = fcf[0] if fcf else None
    m["fcf"] = fcf0
    m["fcf_margin"] = safe_div(fcf0, rev0)
    ni0 = pick(inc[0], "netIncome") if inc else None
    m["fcf_conversion"] = safe_div(fcf0, ni0) if ni0 and ni0 > 0 else None

    # ------------------------------------------------------------------ health
    m["debt_to_equity"] = pick(r, "debtToEquityRatioTTM", "debtEquityRatioTTM")
    m["current_ratio"] = pick(r, "currentRatioTTM")
    m["interest_coverage"] = pick(r, "interestCoverageRatioTTM")
    m["net_debt_ebitda"] = pick(k, "netDebtToEBITDATTM")

    # --------------------------------------------------------------- valuation
    m["ps"] = _pos(pick(r, "priceToSalesRatioTTM"))
    m["pb"] = _pos(pick(r, "priceToBookRatioTTM"))
    m["p_fcf"] = _pos(pick(r, "priceToFreeCashFlowRatioTTM")) or _pos(safe_div(mcap, fcf0))
    m["ev_ebitda"] = _pos(pick(k, "evToEBITDATTM") or pick(r, "enterpriseValueMultipleTTM"))
    m["fcf_yield"] = pick(k, "freeCashFlowYieldTTM") if pick(k, "freeCashFlowYieldTTM") is not None else safe_div(fcf0, mcap)
    m["book_value_ps"] = pick(r, "bookValuePerShareTTM") or pick(k, "bookValuePerShareTTM") or (
        safe_div(price, m["pb"]) if m["pb"] else None
    )

    # ---------------------------------------------------------------- momentum
    m["ret_1m"] = _price_return(c.prices, 30)
    m["ret_3m"] = _price_return(c.prices, 91)
    m["ret_6m"] = _price_return(c.prices, 182)
    m["ret_12m"] = _price_return(c.prices, 365)
    hi = None
    if c.prices:
        yr = [pick(p, "price", "close") for p in c.prices[-252:]]
        yr = [v for v in yr if v]
        hi = max(yr) if yr else None
    if hi is None:
        rng = str(c.profile.get("range", ""))
        if "-" in rng:
            hi = num(rng.split("-")[-1])
    m["pct_from_52w_high"] = (price / hi - 1) if (price and hi) else None

    # ----------------------------------------------------------------- outlook
    m["price_target"] = pick(c.price_target, "targetConsensus", "targetMedian")
    m["price_target_upside"] = (m["price_target"] / price - 1) if (m["price_target"] and price) else None
    beats = []
    for e in sorted(c.earnings, key=lambda e: str(e.get("date")), reverse=True):
        d = parse_date(e.get("date"))
        a, s = pick(e, "epsActual"), pick(e, "epsEstimated")
        if d and d <= today and a is not None and s is not None:
            beats.append(a > s)
        if len(beats) == 8:
            break
    m["eps_beat_rate"] = (sum(beats) / len(beats)) if len(beats) >= 4 else None

    shs = _series(inc, "weightedAverageShsOutDil", "weightedAverageShsOut")
    m["share_change_3y"] = (shs[0] / shs[min(3, len(shs) - 1)] - 1) if len(shs) > 1 and shs[0] and shs[min(3, len(shs) - 1)] else None
    return m
