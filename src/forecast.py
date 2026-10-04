"""Revenue / EPS forecast table (actuals + analyst consensus + fade extrapolation) and surprise history."""
from __future__ import annotations

from datetime import date

import pandas as pd

from .models import CompanyData
from .valuation import Assumptions
from .utils import parse_date, pick


def build_forecast(c: CompanyData, m: dict, a: Assumptions | None = None, today=None, extrapolate_years=2) -> pd.DataFrame:
    a = a or Assumptions()
    today = today or date.today()
    rows = []
    for r in reversed(c.income[:5]):
        d = parse_date(r.get("date"))
        if d:
            rows.append({"year": d.year, "revenue": pick(r, "revenue"), "eps": pick(r, "epsDiluted", "eps"),
                         "net_income": pick(r, "netIncome"), "kind": "actual", "eps_low": None, "eps_high": None, "analysts": None})
    seen = {r["year"] for r in rows}
    for e in sorted(c.estimates, key=lambda e: str(e.get("date"))):
        d = parse_date(e.get("date"))
        if d and d > today and d.year not in seen:
            rows.append({"year": d.year, "revenue": pick(e, "revenueAvg"), "eps": pick(e, "epsAvg"),
                         "net_income": pick(e, "netIncomeAvg"), "kind": "analyst",
                         "eps_low": pick(e, "epsLow"), "eps_high": pick(e, "epsHigh"),
                         "analysts": pick(e, "numAnalystsEps", "numberAnalystEstimatedEps")})
            seen.add(d.year)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("year").reset_index(drop=True)
    df["revenue_growth"] = df["revenue"].pct_change()
    df["eps_growth"] = df["eps"].where(df["eps"] > 0).pct_change(fill_method=None)

    # fade the last observed growth toward terminal growth for a couple more years
    last = df.iloc[-1]
    g_rev = last["revenue_growth"] if pd.notna(last["revenue_growth"]) else m.get("rev_cagr_3y")
    g_eps = last["eps_growth"] if pd.notna(last["eps_growth"]) else (m.get("eps_cagr_3y"))
    ext = []
    rev, eps = last["revenue"], last["eps"]
    for i in range(1, extrapolate_years + 1):
        fade = 0.75 ** i
        gr = a.terminal_growth + ((g_rev if g_rev is not None else a.terminal_growth) - a.terminal_growth) * fade
        ge = a.terminal_growth + ((g_eps if g_eps is not None else a.terminal_growth) - a.terminal_growth) * fade
        gr, ge = max(min(gr, a.max_growth), a.min_growth), max(min(ge, a.max_growth), a.min_growth)
        rev = rev * (1 + gr) if pd.notna(rev) else None
        eps = eps * (1 + ge) if pd.notna(eps) and eps > 0 else eps
        ext.append({"year": int(last["year"]) + i, "revenue": rev, "eps": eps, "net_income": None, "kind": "extrapolated",
                    "revenue_growth": gr, "eps_growth": ge, "eps_low": None, "eps_high": None, "analysts": None})
    return pd.concat([df, pd.DataFrame(ext).dropna(axis=1, how="all")], ignore_index=True)


def earnings_surprises(c: CompanyData, today=None):
    """Return (history DataFrame, next earnings date or None)."""
    today = today or date.today()
    rows, nxt = [], None
    for e in sorted(c.earnings, key=lambda e: str(e.get("date"))):
        d = parse_date(e.get("date"))
        if not d:
            continue
        act, est = pick(e, "epsActual"), pick(e, "epsEstimated")
        if act is None and d >= today:
            nxt = nxt or d
            continue
        if act is not None and est is not None and d <= today:
            rows.append({"date": d, "eps_actual": act, "eps_estimate": est,
                         "surprise_pct": (act - est) / abs(est) if est else None, "beat": act > est})
    df = pd.DataFrame(rows).sort_values("date", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()
    return df, nxt
