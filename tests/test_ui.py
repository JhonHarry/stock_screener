"""Smoke-test the Streamlit pages with a stubbed data layer (no network, no API key)."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from tests.test_core import make_company  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def stub(monkeypatch, tmp_path):
    import src.analysis as analysis

    monkeypatch.setattr(analysis, "load_company", lambda client, symbol, deep=True: make_company())
    monkeypatch.setenv("VS_RESULTS_PATH", str(tmp_path / "results.csv"))
    monkeypatch.setenv("VS_CACHE_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("FMP_API_KEY", "test")


def test_company_page_renders(stub):
    at = AppTest.from_file(str(ROOT / "pages/2_Company.py"), default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("Test Co" in h.value for h in at.header)


def test_screener_with_results(stub):
    from src.analysis import analyze_company
    from src.store import upsert
    from src.valuation import Assumptions
    from tests.test_core import TODAY

    rows = []
    for sym, price in (("AAA", 60.0), ("BBB", 100.0), ("CCC", 190.0)):
        c = make_company(price=price)
        c.symbol = sym
        rows.append(analyze_company(c, Assumptions(), TODAY).to_row())
    upsert(rows)
    for page in ("app.py", "pages/1_Screener.py"):
        at = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
        assert not at.exception, (page, at.exception)
    at = AppTest.from_file(str(ROOT / "pages/1_Screener.py"), default_timeout=60).run()
    preset = next(s for s in at.selectbox if s.label == "Preset")
    preset.select("Dividend growth").run()
    assert not at.exception, at.exception


def test_other_pages_render(stub):
    for page in ("app.py", "pages/1_Screener.py", "pages/3_Methodology.py"):
        at = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
        assert not at.exception, (page, at.exception)
