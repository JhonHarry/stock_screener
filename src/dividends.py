"""Dividend analytics (yield, growth, payout, safety/consistency grades)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .models import CompanyData
from .scoring import avg, lin, to_grade
from .utils import cagr, median, parse_date, pick, safe_div

EMPTY = {
    "payer": False, "ttm_dividend": 0.0, "forward_dividend": None, "yield_ttm": None, "yield_fwd": None,
    "frequency": None, "cagr_3y": None, "cagr_5y": None, "years_no_cut": 0, "years_growth": 0,
    "payout_eps": None, "payout_fcf": None, "last_change_pct": None, "annual": {}, "grades": {},
}


def _yield_score(y):
    if y is None or y <= 0:
        return None
    if y <= 0.07:
        return lin(y, 0.005, 0.04)
    return max(40.0, 100.0 - (y - 0.07) * 1500)  # very high yields often signal distress


def analyze_dividends(c: CompanyData, m: dict, today=None) -> dict:
    today = today or date.today()
    rows = []
    for d in c.dividends:
        dt, amt = parse_date(d.get("date")), pick(d, "adjDividend", "dividend")
        if dt and amt and amt > 0:
            rows.append((dt, amt))
    rows.sort()
    out = dict(EMPTY)
    if not rows:
        return out

    ttm = sum(a for d, a in rows if d > today - timedelta(days=365))
    if ttm <= 0:
        return out  # dividend discontinued
    price = m.get("price")

    by_year = defaultdict(lambda: [0.0, 0])
    for d, a in rows:
        by_year[d.year][0] += a
        by_year[d.year][1] += 1
    years = sorted(y for y in by_year if y < today.year)
    if len(years) >= 3 and by_year[years[0]][1] < median([by_year[y][1] for y in years]):
        years = years[1:]  # first year of history is usually partial
    totals = {y: by_year[y][0] for y in years}

    freq = median([by_year[y][1] for y in years]) if years else None
    if not freq:
        freq = sum(1 for d, _ in rows if d > today - timedelta(days=365))
    freq = int(round(freq)) if freq else None
    fwd = rows[-1][1] * freq if freq and 1 <= freq <= 12 else None

    def cagr_n(n):
        if len(years) >= n + 1 and years[-1] - years[-1 - n] == n:
            return cagr(totals[years[-1]], totals[years[-1 - n]], n)
        return None

    no_cut = growth = 0
    for y in reversed(years):
        if y - 1 in totals and totals[y] >= totals[y - 1] * 0.995:
            no_cut += 1
        else:
            break
    for y in reversed(years):
        if y - 1 in totals and totals[y] > totals[y - 1] * 1.005:
            growth += 1
        else:
            break

    last_change = safe_div(rows[-1][1], rows[-2][1]) - 1 if len(rows) > 1 else None

    eps = m.get("eps_ttm")
    payout_eps = safe_div(ttm, eps) if eps and eps > 0 else None
    fcf = m.get("fcf")
    paid = pick(c.cashflow[0], "commonDividendsPaid", "netDividendsPaid", "dividendsPaid") if c.cashflow else None
    paid = abs(paid) if paid else (ttm * c.shares if c.shares else None)
    payout_fcf = safe_div(paid, fcf) if fcf and fcf > 0 else None

    out.update(
        payer=True, ttm_dividend=ttm, forward_dividend=fwd, frequency=freq,
        yield_ttm=safe_div(ttm, price), yield_fwd=safe_div(fwd, price),
        cagr_3y=cagr_n(3), cagr_5y=cagr_n(5), years_no_cut=no_cut, years_growth=growth,
        payout_eps=payout_eps, payout_fcf=payout_fcf, last_change_pct=last_change, annual=totals,
    )

    safety = avg([
        lin(payout_eps, 1.0, 0.40) if payout_eps is not None else (0.0 if eps is not None and eps <= 0 else None),
        lin(payout_fcf, 1.0, 0.35) if payout_fcf is not None else (0.0 if fcf is not None and fcf <= 0 else None),
        lin(m.get("interest_coverage"), 2, 12),
        lin(m.get("net_debt_ebitda"), 4.0, 0.5),
    ])
    growth_s = avg([lin(out["cagr_3y"], 0, 0.10), lin(out["cagr_5y"], 0, 0.10), lin(growth, 0, 10)])
    yield_s = _yield_score(out["yield_ttm"])
    consist = avg([lin(no_cut, 0, 10), lin(growth, 0, 10)]) if years else None
    out["grades"] = {
        "Safety": {"score": safety, "grade": to_grade(safety)},
        "Growth": {"score": growth_s, "grade": to_grade(growth_s)},
        "Yield": {"score": yield_s, "grade": to_grade(yield_s)},
        "Consistency": {"score": consist, "grade": to_grade(consist)},
    }
    return out


def project_income(shares_owned, price, yield_now, growth, years=10):
    """Simple projection of annual dividend income (no reinvestment) and yield on cost."""
    rows = []
    div0 = shares_owned * price * (yield_now or 0)
    cost = shares_owned * price
    for t in range(0, years + 1):
        inc = div0 * (1 + (growth or 0)) ** t
        rows.append({"year": t, "annual_income": inc, "yield_on_cost": inc / cost if cost else None})
    return rows
