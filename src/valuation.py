"""Intrinsic-value models: DCF, Graham, EPS x exit multiple, dividend discount."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .models import CompanyData
from .utils import clip, median, pick, safe_div


@dataclass(frozen=True)
class Assumptions:
    risk_free: float = 0.043          # 10y Treasury, approx.
    equity_risk_premium: float = 0.05
    terminal_growth: float = 0.025
    min_growth: float = -0.05         # clamp on stage-1 growth
    max_growth: float = 0.20
    aaa_yield: float = 0.05           # Graham formula
    pe_floor: float = 10.0
    pe_cap: float = 25.0
    buy_margin: float = 0.20          # margin of safety wanted before calling it a buy


def capm_rate(beta, a: Assumptions):
    b = beta if beta is not None else 1.0
    return clip(a.risk_free + b * a.equity_risk_premium, 0.07, 0.12)


def base_fcf(c: CompanyData):
    vals = [pick(r, "freeCashFlow") for r in c.cashflow[:3]]
    vals = [v for v in vals if v is not None]
    if not vals or vals[0] <= 0:
        return None
    if len(vals) >= 2 and all(v > 0 for v in vals):
        return 0.6 * vals[0] + 0.4 * (sum(vals) / len(vals))  # smooth one-off spikes
    return vals[0]


def pick_growth(m: dict, a: Assumptions):
    hist = median([m.get("fcf_cagr_3y"), m.get("eps_cagr_3y"), m.get("rev_cagr_3y")])
    fwd = m.get("fwd_eps_growth")
    if fwd is not None and hist is not None:
        g, src = 0.6 * fwd + 0.4 * hist, "60% analyst EPS growth + 40% historical median"
    elif fwd is not None:
        g, src = fwd, "analyst EPS growth"
    elif hist is not None:
        g, src = hist, "historical median growth"
    else:
        g, src = None, "unavailable"
    return clip(g, a.min_growth, a.max_growth), src


def dcf_schedule(fcf0, g1, r, g_term, years1=5, years2=5):
    """Two-stage DCF cash-flow schedule; growth fades linearly in stage 2."""
    rows, fcf = [], fcf0
    for t in range(1, years1 + years2 + 1):
        g = g1 if t <= years1 else g1 + (g_term - g1) * (t - years1) / years2
        fcf *= 1 + g
        rows.append({"year": t, "growth": g, "fcf": fcf, "pv": fcf / (1 + r) ** t})
    return rows


def dcf_value(fcf0, shares, g1, r, g_term, years1=5, years2=5):
    if not fcf0 or fcf0 <= 0 or not shares or g1 is None or r <= g_term:
        return None
    sched = dcf_schedule(fcf0, g1, r, g_term, years1, years2)
    tv = sched[-1]["fcf"] * (1 + g_term) / (r - g_term)
    total = sum(x["pv"] for x in sched) + tv / (1 + r) ** (years1 + years2)
    return total / shares


def reverse_dcf(price, fcf0, shares, r, g_term):
    """Stage-1 FCF growth the current price implies (bisection)."""
    if not (price and fcf0 and fcf0 > 0 and shares) or r <= g_term:
        return None
    lo, hi = -0.30, 0.60
    f = lambda g: dcf_value(fcf0, shares, g, r, g_term) - price
    if f(lo) > 0 or f(hi) < 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return (lo + hi) / 2


def graham_number(eps, bvps):
    if eps and bvps and eps > 0 and bvps > 0:
        return math.sqrt(22.5 * eps * bvps)
    return None


def graham_growth(eps, g, a: Assumptions):
    """Graham's revised formula: V = EPS x (8.5 + 2g) x 4.4 / Y."""
    if not eps or eps <= 0 or g is None:
        return None
    g_pct = clip(g * 100, 0, 15)
    return eps * (8.5 + 2 * g_pct) * 4.4 / (a.aaa_yield * 100)


def eps_multiple(eps, g, r, a: Assumptions, years=5):
    """EPS in ``years`` x exit P/E, discounted back at the required return."""
    if not eps or eps <= 0 or g is None:
        return None
    exit_pe = clip(8.5 + 1.5 * (g * 100), a.pe_floor, a.pe_cap)
    return eps * (1 + g) ** years * exit_pe / (1 + r) ** years


def ddm(d_fwd, g_div, r, g_term, years=5):
    if not d_fwd or d_fwd <= 0 or r <= g_term:
        return None
    g = clip(g_div if g_div is not None else g_term, 0.0, 0.08)
    pv, d = 0.0, d_fwd
    for t in range(1, years + 1):
        pv += d / (1 + r) ** t
        d *= 1 + g
    return pv + d / (r - g_term) / (1 + r) ** years


def verdict(upside):
    if upside is None:
        return "Not enough data"
    if upside >= 0.35:
        return "Deeply undervalued"
    if upside >= 0.10:
        return "Undervalued"
    if upside > -0.10:
        return "Fairly valued"
    if upside > -0.30:
        return "Overvalued"
    return "Significantly overvalued"


def sensitivity(fcf0, shares, g_term, rates, growths):
    return {(r, g): dcf_value(fcf0, shares, g, r, g_term) for r in rates for g in growths}


def run_valuation(c: CompanyData, m: dict, div: dict, a: Assumptions | None = None) -> dict:
    a = a or Assumptions()
    price, shares = m.get("price"), c.shares
    g, g_src = pick_growth(m, a)
    r = capm_rate(c.beta, a)
    fcf0 = base_fcf(c)
    eps = m.get("eps_ttm")

    models = {
        "DCF (FCF, 10-year)": dcf_value(fcf0, shares, g, r, a.terminal_growth),
        "Graham growth formula": graham_growth(m.get("fwd_eps") or eps, g, a),
        "5-yr EPS x exit P/E": eps_multiple(eps, g, r, a),
    }
    if div.get("payer") and (div.get("yield_ttm") or 0) >= 0.015:
        models["Dividend discount"] = ddm(div.get("forward_dividend") or div["ttm_dividend"], div.get("cagr_5y") or div.get("cagr_3y"), r, a.terminal_growth)
    models = {k: (v if v and v > 0 else None) for k, v in models.items()}
    used = [v for v in models.values() if v]

    fv = median(used)
    upside = safe_div(fv, price) - 1 if fv and price else None
    entry = fv * (1 - a.buy_margin) if fv else None
    pt = m.get("price_target")
    return {
        "fair_value": fv,
        "fair_low": min(used) if used else None,
        "fair_high": max(used) if used else None,
        "upside": upside,
        "verdict": verdict(upside),
        "entry_price": entry,
        "n_models": len(used),
        "confidence": "High" if len(used) >= 3 else "Medium" if len(used) == 2 else "Low",
        "models": [{"model": k, "value": v, "upside": (v / price - 1) if (v and price) else None} for k, v in models.items()],
        "graham_number": graham_number(eps, m.get("book_value_ps")),
        "analyst_target": pt,
        "analyst_upside": m.get("price_target_upside"),
        "growth": g, "growth_source": g_src, "discount_rate": r, "terminal_growth": a.terminal_growth,
        "base_fcf": fcf0, "implied_growth": reverse_dcf(price, fcf0, shares, r, a.terminal_growth),
        "schedule": dcf_schedule(fcf0, g, r, a.terminal_growth) if (fcf0 and g is not None) else [],
    }
