"""Orchestrates loading, metrics, grading, valuation, dividends, forecast and insights."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from .dividends import analyze_dividends
from .forecast import build_forecast, earnings_surprises
from .insights import build_insights
from .metrics import compute_metrics
from .models import CompanyData, load_company
from .scoring import grade_all, overall_rating
from .valuation import Assumptions, run_valuation


@dataclass
class Analysis:
    company: CompanyData
    metrics: dict
    grades: dict
    overall: dict
    dividend: dict
    valuation: dict
    forecast: pd.DataFrame
    surprises: pd.DataFrame
    next_earnings: object
    insights: dict

    def to_row(self) -> dict:
        c, m, v, d = self.company, self.metrics, self.valuation, self.dividend
        row = {
            "symbol": c.symbol, "name": c.name, "sector": c.sector, "industry": c.industry,
            "price": m["price"], "market_cap": m["market_cap"],
            "overall_score": self.overall["score"], "overall_grade": self.overall["grade"], "rating": self.overall["rating"],
            "fair_value": v["fair_value"], "upside": v["upside"], "verdict": v["verdict"], "entry_price": v["entry_price"],
            "action": self.insights["action"],
            "dividend_yield": d.get("yield_ttm"), "payout_eps": d.get("payout_eps"), "payout_fcf": d.get("payout_fcf"),
            "div_cagr_5y": d.get("cagr_5y"), "div_years_growth": d.get("years_growth"),
            "div_safety": d.get("grades", {}).get("Safety", {}).get("grade"),
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        for k in ("pe", "fwd_pe", "peg", "ps", "p_fcf", "ev_ebitda", "fcf_yield", "rev_cagr_3y", "eps_cagr_3y",
                  "fwd_eps_growth", "gross_margin", "net_margin", "roe", "roic", "debt_to_equity",
                  "ret_6m", "ret_12m", "price_target_upside"):
            row[k] = m.get(k)
        for f, gr in self.grades.items():
            key = f.lower().replace(" ", "_")
            row[f"{key}_grade"], row[f"{key}_score"] = gr["grade"], gr["score"]
        return row


def analyze_company(c: CompanyData, assumptions: Assumptions | None = None, today: date | None = None) -> Analysis:
    a = assumptions or Assumptions()
    m = compute_metrics(c, today)
    div = analyze_dividends(c, m, today)
    val = run_valuation(c, m, div, a)
    grades = grade_all(m)
    overall = overall_rating(grades)
    fc = build_forecast(c, m, a, today)
    sur, nxt = earnings_surprises(c, today)
    ins = build_insights(c, m, div, val, grades, overall)
    return Analysis(c, m, grades, overall, div, val, fc, sur, nxt, ins)


def analyze(client, symbol: str, deep: bool = True, assumptions: Assumptions | None = None) -> Analysis:
    return analyze_company(load_company(client, symbol, deep=deep), assumptions)
