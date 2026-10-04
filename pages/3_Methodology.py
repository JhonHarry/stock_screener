import streamlit as st

from src import ui
from src.scoring import FACTOR_RULES, WEIGHTS

st.set_page_config(page_title="Methodology", page_icon="📘", layout="wide")
ui.sidebar_api()
st.title("📘 Methodology & limits")

st.markdown(
    """
**This is not Seeking Alpha's Quant rating.** Their model is proprietary and ranks each metric against sector peers.
Here every metric is mapped linearly to 0-100 between a "bad" and a "good" anchor (below) and a factor grade is the
average of the metrics that exist. Anchors are my judgement, so tune them in `src/scoring.py`.

**Fair value** is the median of up to four models: a 10-year two-stage DCF on free cash flow (discount rate from CAPM,
clamped to 7-12%), Graham's growth formula, 5-year EPS times an exit P/E, and a dividend-discount model for payers
yielding 1.5%+. Growth blends analyst EPS growth with the historical median. A *reverse DCF* shows the growth the price implies.

**Dividend grades:** Safety (payout vs earnings and FCF, coverage, leverage), Growth (3/5-year CAGR, raise streak),
Yield (penalised above 7%), Consistency (years without a cut / with raises, limited to the history your plan returns).

**Free-plan caveats:** about 250 calls per day, US tickers only, and some endpoints (e.g. analyst estimates) may be restricted.
Missing data is skipped, never invented, and a stock with too little data shows "Not enough data".
Always confirm numbers with the company's filings.
"""
)
st.subheader("Factor metrics (bad anchor → good anchor)")
for factor, rules in FACTOR_RULES.items():
    with st.expander(f"{factor} · weight {WEIGHTS[factor]:.0%}"):
        st.table({"Metric": [r[0] for r in rules], "Score 0 at": [r[1] for r in rules], "Score 100 at": [r[2] for r in rules]})
st.caption(ui.DISCLAIMER)
