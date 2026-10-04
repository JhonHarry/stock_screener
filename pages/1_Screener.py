import pandas as pd
import streamlit as st

from src import ui
from src.analysis import analyze
from src.fmp import FMPError, RateLimitError, SymbolNotFound
from src.store import load_results, load_universe, stale_symbols, upsert

st.set_page_config(page_title="Screener", page_icon="🔎", layout="wide")
client = ui.sidebar_api()
st.title("🔎 Screener")

PRESETS = {
    "Undervalued quality": lambda d: d[(d["rating"].isin(["Strong Buy", "Buy"])) & (d["upside"] >= 0.10)],
    "Dividend growth": lambda d: d[(d["dividend_yield"] >= 0.015) & (d["div_years_growth"] >= 5) & (d["div_safety"].fillna("F").str[0].isin(list("ABC")))],
    "Growth at a reasonable price": lambda d: d[(d["fwd_eps_growth"] >= 0.10) & (d["peg"] <= 2) & (d["profitability_score"] >= 60)],
    "Deep value": lambda d: d[(d["upside"] >= 0.30)],
    "All": lambda d: d,
}

# ---------------------------------------------------------------- analyse more
with st.expander("Add or refresh stocks", expanded=load_results().empty):
    st.caption("Each new stock costs ~7 API calls (lean) or ~10 (deep). Cached stocks cost nothing. The free plan allows ~250 calls/day.")
    tickers = st.text_input("Tickers (comma separated)", placeholder="AAPL, MSFT, KO")
    c1, c2, c3 = st.columns(3)
    deep = c1.checkbox("Deep mode (momentum, targets, earnings history)", value=False)
    n_stale = c2.number_input("…or refresh N stalest from universe.csv", 0, 100, 0)
    go = c3.button("Analyse", type="primary", disabled=client is None)
    if go and client:
        todo = [t.strip().upper() for t in tickers.replace(";", ",").split(",") if t.strip()]
        if n_stale:
            todo += stale_symbols(load_universe(), load_results())[: int(n_stale)]
        todo = list(dict.fromkeys(todo))
        bar, rows = st.progress(0.0), []
        for i, s in enumerate(todo):
            bar.progress(i / max(1, len(todo)), text=f"Analysing {s} ({i + 1}/{len(todo)})")
            try:
                rows.append(analyze(client, s, deep=deep).to_row())
            except SymbolNotFound as e:
                st.warning(str(e))
            except RateLimitError as e:
                st.error(str(e))
                break
            except FMPError as e:
                st.error(str(e))
                break
        bar.empty()
        if rows:
            upsert(rows)
            st.success(f"Updated {len(rows)} stocks.")
            st.rerun()

df = load_results()
if df.empty:
    st.info("No results yet. Add some tickers above.")
    st.stop()

# --------------------------------------------------------------------- filters
with st.sidebar:
    st.subheader("Filters")
    preset = st.selectbox("Preset", list(PRESETS))
    sectors = sorted(df["sector"].dropna().unique())
    sel_sectors = st.multiselect("Sector", sectors)
    min_score = st.slider("Min overall score", 0, 100, 0)
    min_up = st.slider("Min upside to fair value (%)", -50, 100, -50)
    min_yield = st.slider("Min dividend yield (%)", 0.0, 8.0, 0.0, 0.1)
    max_pe = st.number_input("Max forward P/E (0 = no limit)", 0.0, 200.0, 0.0)

view = PRESETS[preset](df.copy())
if sel_sectors:
    view = view[view["sector"].isin(sel_sectors)]
view = view[(view["overall_score"].fillna(0) >= min_score) & (view["upside"].fillna(-1) * 100 >= min_up)]
if min_yield:
    view = view[view["dividend_yield"].fillna(0) * 100 >= min_yield]
if max_pe:
    view = view[view["fwd_pe"].between(0.01, max_pe)]
view = view.sort_values("overall_score", ascending=False)

st.caption(f"{len(view)} of {len(df)} stocks match · last update {df['updated'].max()}")
cols = ["symbol", "name", "sector", "price", "fair_value", "upside", "rating", "overall_grade", "valuation_grade", "growth_grade",
        "profitability_grade", "financial_health_grade", "momentum_grade", "dividend_yield", "div_safety", "pe", "fwd_pe", "peg",
        "roic", "eps_cagr_3y", "action"]
cols = [c for c in cols if c in view.columns]
st.dataframe(
    view[cols], hide_index=True, width="stretch", height=520,
    column_config={
        "price": st.column_config.NumberColumn("Price", format="$%.2f"),
        "fair_value": st.column_config.NumberColumn("Fair value", format="$%.2f"),
        "upside": st.column_config.NumberColumn("Upside", format="percent"),
        "dividend_yield": st.column_config.NumberColumn("Yield", format="percent"),
        "roic": st.column_config.NumberColumn("ROIC", format="percent"),
        "eps_cagr_3y": st.column_config.NumberColumn("EPS CAGR 3y", format="percent"),
        "pe": st.column_config.NumberColumn("P/E", format="%.1f"),
        "fwd_pe": st.column_config.NumberColumn("Fwd P/E", format="%.1f"),
        "peg": st.column_config.NumberColumn("PEG", format="%.2f"),
        "overall_grade": "Grade", "valuation_grade": "Val", "growth_grade": "Gr", "profitability_grade": "Prof",
        "financial_health_grade": "Health", "momentum_grade": "Mom", "div_safety": "Div safety",
    },
)
left, right = st.columns([3, 1])
pick = left.selectbox("Open a company", view["symbol"].tolist() if len(view) else [])
if right.button("Open ▶", disabled=not pick):
    st.session_state["symbol"] = pick
    st.switch_page("pages/2_Company.py")
st.download_button("Download CSV", view.to_csv(index=False), "screener.csv", "text/csv")
st.caption(ui.DISCLAIMER)
