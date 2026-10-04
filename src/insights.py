"""Green/red flags, a buy checklist and a plain-language suggestion."""
from __future__ import annotations


def _pct(x):
    return f"{x * 100:.1f}%"


def build_insights(c, m, div, val, grades, overall) -> dict:
    green, red = [], []
    g = lambda k: m.get(k)

    # ----- red flags
    if g("eps_ttm") is not None and g("eps_ttm") <= 0:
        red.append("Not profitable: trailing EPS is negative.")
    if g("fcf") is not None and g("fcf") < 0:
        red.append("Negative free cash flow.")
    if g("fcf_conversion") is not None and g("fcf_conversion") < 0.6:
        red.append(f"Weak earnings quality: FCF is only {_pct(g('fcf_conversion'))} of net income.")
    if div.get("payer"):
        if div.get("payout_eps") is not None and div["payout_eps"] > 0.9:
            red.append(f"Dividend payout is {_pct(div['payout_eps'])} of earnings (little cushion).")
        if div.get("payout_fcf") is not None and div["payout_fcf"] > 1.0:
            red.append("Dividend exceeds free cash flow.")
        if div.get("last_change_pct") is not None and div["last_change_pct"] < -0.05:
            red.append(f"Latest dividend was cut by {_pct(-div['last_change_pct'])}.")
    if g("interest_coverage") is not None and 0 < g("interest_coverage") < 3:
        red.append(f"Thin interest coverage ({g('interest_coverage'):.1f}x).")
    if g("net_debt_ebitda") is not None and g("net_debt_ebitda") > 4:
        red.append(f"High leverage: net debt / EBITDA {g('net_debt_ebitda'):.1f}x.")
    if g("rev_cagr_3y") is not None and g("rev_cagr_3y") < 0:
        red.append(f"Revenue is shrinking ({_pct(g('rev_cagr_3y'))} per year).")
    if g("share_change_3y") is not None and g("share_change_3y") > 0.05:
        red.append(f"Share count up {_pct(g('share_change_3y'))} in 3 years (dilution).")
    if g("ret_12m") is not None and g("ret_12m") < -0.30:
        red.append(f"Down {_pct(-g('ret_12m'))} over 12 months: check whether the business has changed.")
    if val.get("upside") is not None and val["upside"] < -0.30:
        red.append("Trades well above model fair value.")

    # ----- green flags
    if g("roic") is not None and g("roic") >= 0.15:
        green.append(f"High return on invested capital ({_pct(g('roic'))}).")
    if g("roic") is not None and g("roic") >= 0.15 and (g("gross_margin") or 0) >= 0.40:
        green.append("Moat proxy: high ROIC together with a 40%+ gross margin.")
    if g("fcf_conversion") is not None and g("fcf_conversion") >= 0.9:
        green.append(f"Strong cash conversion ({_pct(g('fcf_conversion'))} of net income).")
    if g("share_change_3y") is not None and g("share_change_3y") <= -0.03:
        green.append(f"Net buybacks: share count down {_pct(-g('share_change_3y'))} in 3 years.")
    if g("net_debt_ebitda") is not None and g("net_debt_ebitda") < 0:
        green.append("Net cash balance sheet.")
    if div.get("years_growth", 0) >= 5:
        green.append(f"Dividend raised {div['years_growth']} years in a row (within the data returned).")
    if g("eps_beat_rate") is not None and g("eps_beat_rate") >= 0.75:
        green.append(f"Beat EPS estimates in {_pct(g('eps_beat_rate'))} of the last quarters.")
    if val.get("upside") is not None and val["upside"] >= 0.20:
        green.append(f"Trades {_pct(val['upside'])} below model fair value.")
    if g("peg") is not None and g("peg") < 1.5:
        green.append(f"Reasonable PEG ({g('peg'):.2f}).")

    # ----- notes
    notes = []
    ig, gg = val.get("implied_growth"), val.get("growth")
    if ig is not None and gg is not None:
        notes.append(
            f"Reverse DCF: today's price implies about {_pct(ig)} annual FCF growth for 5 years "
            f"(model assumes {_pct(gg)}). The lower the implied number versus what the business can deliver, the better the margin of safety."
        )

    # ----- checklist
    gr = lambda f: grades[f]["score"]
    checklist = [
        ("Quality: profitability grade B- or better", (gr("Profitability") or 0) >= 60, grades["Profitability"]["grade"]),
        ("Value: at least 10% below fair value", (val.get("upside") or -1) >= 0.10, _pct(val["upside"]) if val.get("upside") is not None else "n/a"),
        ("Safety: financial health grade C+ or better", (gr("Financial Health") or 0) >= 53, grades["Financial Health"]["grade"]),
        ("Growth: growth grade C+ or better", (gr("Growth") or 0) >= 53, grades["Growth"]["grade"]),
        ("Trend: not in a 12-month slump (> -20%)", (g("ret_12m") is None) or g("ret_12m") > -0.20, _pct(g("ret_12m")) if g("ret_12m") is not None else "n/a"),
        ("No major red flags (fewer than 3)", len(red) < 3, f"{len(red)} found"),
    ]

    # ----- suggestion
    rating, upside, entry = overall.get("rating"), val.get("upside"), val.get("entry_price")
    entry_txt = f" A disciplined entry would be near ${entry:,.2f}." if entry else ""
    if rating in ("Strong Buy", "Buy") and upside is not None and upside >= 0.10:
        action = "Buy candidate"
        text = "Quality and price line up: strong factor grades and a price below fair value. Research the business and risks, then consider building a position gradually." + entry_txt
    elif rating in ("Strong Buy", "Buy"):
        action = "Quality, but fully priced"
        text = "The business scores well but the stock is not clearly cheap. Put it on a watchlist and wait for a pullback." + entry_txt
    elif rating == "Hold" and upside is not None and upside >= 0.25:
        action = "Cheap, mixed quality"
        text = "Valuation looks attractive but factor grades are middling. Find out why it is cheap (cyclical trough, structural decline, or temporary issue) before acting." + entry_txt
    elif rating == "Not enough data":
        action = "Insufficient data"
        text = "Too many metrics are missing (often a free-plan limit). Do not rely on this score."
    else:
        action = "No edge"
        text = "Factor grades and valuation do not make a compelling case right now."
    return {"green": green, "red": red, "notes": notes, "checklist": checklist, "action": action, "suggestion": text}
