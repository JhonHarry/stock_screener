"""Factor grades (A+ .. F) modelled on the Seeking Alpha Quant layout.

Seeking Alpha's real grades are proprietary and sector-relative. These are
transparent, absolute-threshold approximations: every metric is mapped linearly
to 0-100 between a "bad" and a "good" anchor, and the factor score is the mean
of the metrics that are available.
"""
from __future__ import annotations

GRADE_STEPS = [
    (93, "A+"), (87, "A"), (80, "A-"), (73, "B+"), (67, "B"), (60, "B-"),
    (53, "C+"), (47, "C"), (40, "C-"), (33, "D+"), (26, "D"), (20, "D-"), (0, "F"),
]


def lin(x, bad, good):
    """Linear 0-100 score; works for 'lower is better' when good < bad."""
    if x is None or good == bad:
        return None
    return max(0.0, min(100.0, (x - bad) / (good - bad) * 100.0))


def avg(values):
    v = [x for x in values if x is not None]
    return sum(v) / len(v) if v else None


def to_grade(score):
    if score is None:
        return "N/A"
    for cut, g in GRADE_STEPS:
        if score >= cut:
            return g
    return "F"


# metric key, "bad" anchor (score 0), "good" anchor (score 100)
FACTOR_RULES = {
    "Valuation": [
        ("earnings_yield", 0.0, 0.08), ("fwd_pe", 35, 10), ("peg", 3.0, 1.0),
        ("ps", 12, 1.5), ("p_fcf", 40, 10), ("ev_ebitda", 25, 7), ("fcf_yield", 0.0, 0.08),
    ],
    "Growth": [
        ("rev_cagr_3y", 0.0, 0.15), ("eps_cagr_3y", 0.0, 0.20), ("fcf_cagr_3y", 0.0, 0.20),
        ("fwd_rev_growth", 0.0, 0.12), ("fwd_eps_growth", 0.0, 0.15),
    ],
    "Profitability": [
        ("gross_margin", 0.15, 0.60), ("op_margin", 0.05, 0.30), ("net_margin", 0.03, 0.25),
        ("roe", 0.05, 0.25), ("roic", 0.04, 0.20), ("fcf_margin", 0.02, 0.20),
    ],
    "Financial Health": [
        ("debt_to_equity", 2.5, 0.3), ("current_ratio", 0.8, 2.0),
        ("interest_coverage", 1.5, 12), ("net_debt_ebitda", 4.0, 0.0),
    ],
    "Momentum": [
        ("ret_3m", -0.15, 0.15), ("ret_6m", -0.20, 0.30), ("ret_12m", -0.25, 0.50),
        ("pct_from_52w_high", -0.35, -0.03),
    ],
    "Analyst Outlook": [  # stand-in for SA's "EPS Revisions" (revision history needs a paid feed)
        ("price_target_upside", -0.10, 0.25), ("eps_beat_rate", 0.40, 0.90), ("eps_expansion", 0.0, 0.25),
    ],
}

WEIGHTS = {
    "Valuation": 0.25, "Growth": 0.20, "Profitability": 0.20,
    "Financial Health": 0.15, "Momentum": 0.10, "Analyst Outlook": 0.10,
}

RATING_STEPS = [(80, "Strong Buy"), (68, "Buy"), (52, "Hold"), (40, "Sell"), (0, "Strong Sell")]


def grade_all(m: dict) -> dict:
    out = {}
    for factor, rules in FACTOR_RULES.items():
        scores = [lin(m.get(key), bad, good) for key, bad, good in rules]
        s = avg(scores)
        out[factor] = {"score": s, "grade": to_grade(s), "n_metrics": sum(x is not None for x in scores)}
    return out


def overall_rating(grades: dict) -> dict:
    num_, den = 0.0, 0.0
    for f, w in WEIGHTS.items():
        s = grades[f]["score"]
        if s is not None:
            num_ += s * w
            den += w
    if den < 0.5:  # too little data to say anything
        return {"score": None, "grade": "N/A", "rating": "Not enough data"}
    score = num_ / den
    rating = next(name for cut, name in RATING_STEPS if score >= cut)
    return {"score": score, "grade": to_grade(score), "rating": rating}
