"""Small numeric / date helpers shared across the project."""
from __future__ import annotations

import math
from datetime import date, datetime
from statistics import median as _median


def num(x):
    """Return x as a finite float, or None."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def pick(d, *keys):
    """First numeric value found among ``keys`` in dict ``d`` (alias-tolerant)."""
    if not d:
        return None
    for k in keys:
        v = num(d.get(k))
        if v is not None:
            return v
    return None


def safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def cagr(end, start, years):
    """Compound annual growth rate; None unless both values are positive."""
    if end is None or start is None or years <= 0 or end <= 0 or start <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def clip(x, lo, hi):
    if x is None:
        return None
    return max(lo, min(hi, x))


def median(values):
    vals = [v for v in values if v is not None]
    return _median(vals) if vals else None


def parse_date(s):
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
