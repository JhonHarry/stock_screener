from datetime import date

import pytest

from src.analysis import analyze_company
from src.fmp import FMPClient, RateLimitError
from src.models import CompanyData
from src.scoring import lin, to_grade
from src.valuation import Assumptions, dcf_value, reverse_dcf

TODAY = date(2026, 10, 4)


def make_company(price=100.0, with_div=True):
    income = [
        {"date": f"{y}-12-31", "revenue": rev, "netIncome": ni, "epsDiluted": ni / 1000, "grossProfit": rev * 0.5,
         "operatingIncome": rev * 0.25, "weightedAverageShsOutDil": sh}
        for y, rev, ni, sh in [(2025, 20000, 4000, 950), (2024, 18500, 3600, 970), (2023, 17000, 3200, 990), (2022, 15500, 2900, 1000)]
    ]
    cash = [{"date": f"{y}-12-31", "freeCashFlow": f, "commonDividendsPaid": -1200} for y, f in [(2025, 4200), (2024, 3800), (2023, 3300), (2022, 3000)]]
    divs = []
    for y in range(2018, 2026):
        for q in range(4):
            divs.append({"date": f"{y}-{3 * q + 2:02d}-15", "adjDividend": 0.25 * 1.07 ** (y - 2018)})
    divs.append({"date": "2026-02-15", "adjDividend": 0.25 * 1.07 ** 8})
    divs.append({"date": "2026-05-15", "adjDividend": 0.25 * 1.07 ** 8})
    divs.append({"date": "2026-08-15", "adjDividend": 0.25 * 1.07 ** 8})
    return CompanyData(
        symbol="TEST",
        profile={"price": price, "marketCap": price * 1000, "beta": 1.0, "companyName": "Test Co", "sector": "Tech", "lastDividend": 1.7},
        ratios={"priceToEarningsRatioTTM": price / 4.4, "debtToEquityRatioTTM": 0.5, "currentRatioTTM": 1.6,
                "interestCoverageRatioTTM": 12, "priceToSalesRatioTTM": 5, "priceToFreeCashFlowRatioTTM": 24},
        key_metrics={"returnOnInvestedCapitalTTM": 0.18, "returnOnEquityTTM": 0.2, "netDebtToEBITDATTM": 0.8, "evToEBITDATTM": 14},
        income=income, cashflow=cash, dividends=divs if with_div else [],
        estimates=[{"date": "2026-12-31", "epsAvg": 4.7, "revenueAvg": 21500}, {"date": "2027-12-31", "epsAvg": 5.1, "revenueAvg": 23000},
                   {"date": "2028-12-31", "epsAvg": 5.6, "revenueAvg": 24600}],
        price_target={"targetConsensus": 120}, earnings=[{"date": f"2025-{m:02d}-20", "epsActual": 1.1, "epsEstimated": 1.0} for m in (2, 5, 8, 11)],
        prices=[{"date": f"2025-{m:02d}-28", "price": 80 + m} for m in range(1, 13)] + [{"date": "2026-10-02", "price": price}],
    )


def test_lin_and_grades():
    assert lin(5, 0, 10) == 50
    assert lin(5, 10, 0) == 50  # lower-is-better
    assert lin(-5, 0, 10) == 0 and lin(50, 0, 10) == 100 and lin(None, 0, 1) is None
    assert to_grade(95) == "A+" and to_grade(10) == "F" and to_grade(None) == "N/A"


def test_dcf_monotonic_and_reverse():
    low = dcf_value(1000, 100, 0.03, 0.09, 0.025)
    high = dcf_value(1000, 100, 0.10, 0.09, 0.025)
    assert high > low > 0
    assert dcf_value(1000, 100, 0.05, 0.09, 0.025) > dcf_value(1000, 100, 0.05, 0.11, 0.025)
    assert dcf_value(-5, 100, 0.05, 0.09, 0.025) is None
    price = dcf_value(1000, 100, 0.07, 0.09, 0.025)
    assert reverse_dcf(price, 1000, 100, 0.09, 0.025) == pytest.approx(0.07, abs=1e-4)


def test_full_analysis_dividend_payer():
    a = analyze_company(make_company(), Assumptions(), TODAY)
    m, d, v = a.metrics, a.dividend, a.valuation
    assert m["pe"] == pytest.approx(100 / 4.4)
    assert m["rev_cagr_3y"] == pytest.approx((20000 / 15500) ** (1 / 3) - 1)
    assert m["fwd_eps"] == 4.7 and m["fwd_eps_growth"] > 0
    assert m["eps_beat_rate"] == 1.0
    assert d["payer"] and d["years_growth"] >= 5 and d["cagr_5y"] == pytest.approx(0.07, abs=0.005)
    assert 0.01 < d["yield_ttm"] < 0.05
    assert v["fair_value"] and v["n_models"] >= 3 and v["verdict"]
    assert set(a.grades) == {"Valuation", "Growth", "Profitability", "Financial Health", "Momentum", "Analyst Outlook"}
    assert a.overall["rating"] in {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}
    assert (a.forecast["kind"] == "analyst").sum() == 3 and (a.forecast["kind"] == "extrapolated").sum() == 2
    row = a.to_row()
    assert row["symbol"] == "TEST" and "valuation_grade" in row


def test_cheaper_price_gives_more_upside():
    cheap = analyze_company(make_company(price=40), Assumptions(), TODAY).valuation["upside"]
    rich = analyze_company(make_company(price=200), Assumptions(), TODAY).valuation["upside"]
    assert cheap > rich


def test_discontinued_or_no_dividend():
    assert analyze_company(make_company(with_div=False), Assumptions(), TODAY).dividend["payer"] is False
    c = make_company()
    c.dividends = [r for r in c.dividends if r["date"] < "2024-01-01"]
    assert analyze_company(c, Assumptions(), TODAY).dividend["payer"] is False


def test_analysis_survives_missing_data():
    c = CompanyData(symbol="EMPTY", profile={"price": 10, "marketCap": 1000})
    a = analyze_company(c, Assumptions(), TODAY)
    assert a.overall["rating"] == "Not enough data"
    assert a.valuation["fair_value"] is None


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Session:
    def __init__(self, responses):
        self.responses, self.calls = responses, 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def test_client_cache_budget_and_premium(tmp_path):
    s = _Session([_Resp(200, [{"symbol": "X"}]), _Resp(402, {}), _Resp(200, [{"a": 1}])])
    c = FMPClient("k", db_path=tmp_path / "c.sqlite", daily_budget=3, session=s)
    assert c.get_one("profile", symbol="X") == {"symbol": "X"}
    assert c.get_one("profile", symbol="X") == {"symbol": "X"}  # cached
    assert s.calls == 1
    assert c.get_list("analyst-estimates", symbol="X") == []  # 402 -> []
    assert c.get_list("analyst-estimates", symbol="X") == []  # remembered, no new call
    assert s.calls == 2
    c.get_list("dividends", symbol="X")
    with pytest.raises(RateLimitError):
        c.get_list("earnings", symbol="X")
    assert c.calls_today() == 3
