import streamlit as st

from src import ui
from src.store import load_results

st.set_page_config(page_title="Valuation Screener", page_icon="📈", layout="wide")
ui.sidebar_api()

st.title("📈 Valuation Screener")
st.write(
    "Find quality companies trading below fair value. Letter grades for Valuation, Growth, Profitability, Financial Health, "
    "Momentum and Analyst Outlook, a Seeking-Alpha-style dividend tab, earnings forecasts, and four intrinsic-value models."
)
c1, c2, c3 = st.columns(3)
c1.page_link("pages/1_Screener.py", label="Screener: rank many stocks", icon="🔎")
c2.page_link("pages/2_Company.py", label="Company: deep dive on one ticker", icon="🏢")
c3.page_link("pages/3_Methodology.py", label="Methodology & limits", icon="📘")

df = load_results()
st.subheader("Top opportunities in your results")
if df.empty:
    st.info("No results yet. Open the Screener page and analyse a few tickers (or run `python -m src.cli refresh`).")
else:
    top = df[df["rating"].isin(["Strong Buy", "Buy"]) & (df["upside"] > 0.10)].sort_values("overall_score", ascending=False).head(10)
    if top.empty:
        st.write("No Buy-rated stock trading 10%+ below fair value in the current results.")
    else:
        st.dataframe(
            top[["symbol", "name", "sector", "price", "fair_value", "upside", "overall_grade", "rating", "dividend_yield"]],
            hide_index=True, width="stretch",
            column_config={
                "price": st.column_config.NumberColumn(format="$%.2f"), "fair_value": st.column_config.NumberColumn(format="$%.2f"),
                "upside": st.column_config.NumberColumn(format="percent"), "dividend_yield": st.column_config.NumberColumn(format="percent"),
            },
        )
st.caption(ui.DISCLAIMER)
